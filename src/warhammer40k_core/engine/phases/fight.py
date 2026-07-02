from __future__ import annotations

from collections.abc import Callable
from dataclasses import dataclass, field
from typing import TYPE_CHECKING, cast

from warhammer40k_core.core.army_catalog import ArmyCatalog
from warhammer40k_core.core.objectives import ObjectiveMarker
from warhammer40k_core.core.ruleset_descriptor import (
    BattlePhaseKind,
    FightOrderingBandKind,
    FightPhaseStepKind,
    FightPolicyDescriptor,
    FightTypeKind,
    RulesetDescriptor,
)
from warhammer40k_core.core.validation import IdentifierValidator
from warhammer40k_core.engine.attack_sequence import (
    ATTACK_ALLOCATION_DECISION_TYPES,
    ATTACK_RESOLUTION_SELECTION_DECISION_TYPES,
    SELECT_ATTACK_WEAPON_GROUP_DECISION_TYPE,
    SELECT_PSYCHIC_ATTACK_MODIFIER_IGNORES_DECISION_TYPE,
    SELECT_RESOLVE_TARGET_UNIT_DECISION_TYPE,
    AttackSequence,
    apply_allocation_order_decision,
    apply_attack_weapon_group_decision,
    apply_damage_allocation_model_decision,
    apply_destroyed_transport_disembark_proposal_decision,
    apply_destruction_reaction_decision,
    apply_feel_no_pain_decision,
    apply_precision_allocation_decision,
    apply_resolve_target_unit_decision,
    apply_source_backed_attack_dice_reroll_decision,
    build_select_attack_weapon_group_request,
    build_select_resolve_target_unit_request,
    gathered_attack_groups_for_target,
    is_destroyed_transport_disembark_proposal_request,
    resolve_attack_sequence_until_blocked,
    selected_attack_weapon_group_from_result,
    selected_resolve_target_from_result,
    unresolved_target_unit_ids,
    validate_psychic_attack_modifier_ignore_decision,
)
from warhammer40k_core.engine.attack_sequence_completion_hooks import (
    AttackSequenceCompletedContext,
    AttackSequenceCompletedHookRegistry,
    attack_sequence_completed_event_id,
)
from warhammer40k_core.engine.battlefield_state import BattlefieldScenario, PlacementError
from warhammer40k_core.engine.damage_allocation import (
    SELECT_ALLOCATION_ORDER_DECISION_TYPE,
    SELECT_DAMAGE_ALLOCATION_MODEL_DECISION_TYPE,
    SELECT_DESTRUCTION_REACTION_DECISION_TYPE,
    SELECT_FEEL_NO_PAIN_DECISION_TYPE,
    SELECT_PRECISION_ALLOCATION_DECISION_TYPE,
)
from warhammer40k_core.engine.decision_controller import DecisionController
from warhammer40k_core.engine.decision_request import (
    DecisionError,
    DecisionOption,
    DecisionRequest,
    parameterized_decision_option,
)
from warhammer40k_core.engine.decision_result import DecisionResult
from warhammer40k_core.engine.dice import DICE_REROLL_DECISION_TYPE, DiceRollManager
from warhammer40k_core.engine.effects import EffectExpiration, PersistingEffect
from warhammer40k_core.engine.event_log import JsonValue, validate_json_value
from warhammer40k_core.engine.faction_resources import (
    apply_faction_resource_spend_effect,
    faction_resource_result_enriched_payload,
)
from warhammer40k_core.engine.fight_activation_abilities import (
    DECLINE_FIGHT_ACTIVATION_ABILITY_OPTION_ID,
    FIGHT_ACTIVATION_ABILITY_DECISION_TYPE,
    FIGHT_ACTIVATION_ABILITY_EFFECT_KINDS,
    FIGHT_ACTIVATION_MELEE_TARGETING_EFFECT_KIND,
    FightActivationAbilityContext,
    FightActivationAbilityHookRegistry,
    ability_request_activation_payload,
    build_fight_activation_ability_request,
    fight_activation_ability_use_from_result,
    is_fight_activation_ability_decline_payload,
)
from warhammer40k_core.engine.fight_order import (
    DECLINE_FIGHT_INTERRUPT_OPTION_ID,
    ELIGIBLE_TO_FIGHT_PASS_OPTION_ID,
    FIGHT_ACTIVATION_DECISION_TYPE,
    FIGHT_INTERRUPT_DECISION_TYPE,
    FightActivationSelection,
    FightEligibilityContext,
    FightInterruptRequest,
    FightMovementStepState,
    FightPhaseState,
    FightsFirstRegistry,
    current_eligible_pass_from_payload,
    current_fight_activation_selection_from_payload,
    decline_fight_interrupt_payload,
    eligible_fight_contexts_for_player,
    eligible_pass_is_available,
    eligible_pass_option_payload,
    engaged_unit_ids_at_fight_start,
    fight_activation_option_id,
    fight_activation_option_payload,
    fight_interrupt_option_payload,
    fight_interrupt_request_from_payload,
    fight_interrupt_sources_for_player,
    legal_fight_types_for_context,
)
from warhammer40k_core.engine.fight_phase_start_hooks import (
    SELECT_FACTION_RULE_FIGHT_PHASE_START_OPTION_DECISION_TYPE,
    FightPhaseStartHookRegistry,
    FightPhaseStartRequestContext,
    FightPhaseStartResultContext,
)
from warhammer40k_core.engine.fight_resolution import (
    MELEE_DECLARATION_PROPOSAL_KIND,
    SUBMIT_MELEE_DECLARATION_DECISION_TYPE,
    FightMovementProposal,
    FightMovementResolution,
    MeleeDeclarationProposal,
    MeleeDeclarationProposalRequest,
    available_melee_weapons_payloads,
    build_fight_movement_request,
    build_melee_declaration_request,
    fight_movement_maximum_distance_inches,
    fight_movement_proposal_from_payload,
    fight_movement_proposal_payload_parse_failure,
    fight_movement_resolution_violation,
    fight_movement_rule_validation,
    legal_consolidation_modes,
    legal_pile_in_target_unit_ids,
    melee_attack_sequence_from_proposal,
    melee_declaration_proposal_from_payload,
    melee_target_unit_ids,
    record_one_shot_melee_weapon_uses,
    resolve_fight_movement,
    validate_melee_declaration_rules,
)
from warhammer40k_core.engine.fight_unit_selected_hooks import (
    DECLINE_FIGHT_UNIT_GRANT_OPTION_ID,
    SELECT_FIGHT_UNIT_GRANT_DECISION_TYPE,
    FightUnitSelectedContext,
    FightUnitSelectedGrant,
    FightUnitSelectedGrantPayload,
    FightUnitSelectedGrantRegistry,
    FightUnitSelectedHookRegistry,
)
from warhammer40k_core.engine.movement_proposals import (
    MOVEMENT_PROPOSAL_DECISION_TYPE,
    PLACEMENT_PROPOSAL_DECISION_TYPE,
    MovementProposalRequest,
    ProposalKind,
    ProposalValidationResult,
)
from warhammer40k_core.engine.phase import (
    BattlePhase,
    GameLifecycleError,
    GameLifecycleStage,
    LifecycleStatus,
)
from warhammer40k_core.engine.reaction_queue import ReactionQueue
from warhammer40k_core.engine.runtime_modifiers import RuntimeModifierRegistry
from warhammer40k_core.engine.stratagem_catalog import eleventh_edition_stratagem_index
from warhammer40k_core.engine.stratagems import (
    CORE_COUNTEROFFENSIVE_HANDLER_ID,
    CORE_EPIC_CHALLENGE_HANDLER_ID,
    STRATAGEM_TARGET_PROPOSAL_DECISION_TYPE,
    StratagemCatalogIndex,
    StratagemEligibilityContext,
    StratagemTargetProposal,
    request_stratagem_target_proposal,
    stratagem_target_proposal_from_index,
    stratagem_target_proposal_request_payload,
    stratagem_window_declined_for_context,
)
from warhammer40k_core.engine.timing_windows import (
    ReactionWindow,
    TimingTriggerKind,
    TimingWindow,
    TimingWindowDescriptor,
)
from warhammer40k_core.engine.unit_factory import UnitInstance
from warhammer40k_core.geometry.pose import GeometryError

if TYPE_CHECKING:
    from warhammer40k_core.engine.game_state import GameState


_FIGHT_PHASE_COMPLETE_STATUS = "fight_phase_complete"
_FIGHT_PILE_IN_REQUIRED_STATUS = "fight_pile_in_required"
_FIGHT_CONSOLIDATE_REQUIRED_STATUS = "fight_consolidate_required"
_FIGHT_MOVEMENT_COMPLETED_STATUS = "fight_movement_completed"
_FIGHT_MOVEMENT_INVALID_STATUS = "fight_movement_invalid"
_FIGHT_ACTIVATION_REQUIRED_STATUS = "fight_activation_required"
_FIGHT_PASS_RECORDED_STATUS = "eligible_to_fight_pass_recorded"
_FIGHT_ACTIVATION_RECORDED_STATUS = "fight_activation_recorded"
_MELEE_DECLARATION_REQUIRED_STATUS = "melee_declaration_required"
_MELEE_DECLARATION_ACCEPTED_STATUS = "melee_declaration_accepted"
_FIGHT_ACTIVATION_ABILITY_REQUIRED_STATUS = "fight_activation_ability_required"
_FIGHT_ACTIVATION_ABILITY_DECLINED_STATUS = "fight_activation_ability_declined"
_FIGHT_ACTIVATION_ABILITY_USED_STATUS = "fight_activation_ability_used"
_UNIT_FOUGHT_STATUS = "unit_fought"
_FIGHT_INTERRUPT_REQUIRED_STATUS = "fight_interrupt_required"
_FIGHT_INTERRUPT_DECLINED_STATUS = "fight_interrupt_declined"
_FIGHT_INTERRUPT_RECORDED_STATUS = "fight_interrupt_recorded"
_ENDPOINT_ONLY_PATH_VIOLATION_CODE = "endpoint_only_path"


@dataclass(frozen=True, slots=True)
class FightPhaseHandler:
    ruleset_descriptor: RulesetDescriptor | None = None
    army_catalog: ArmyCatalog | None = None
    stratagem_index: StratagemCatalogIndex = field(default_factory=eleventh_edition_stratagem_index)
    fight_activation_ability_hooks: FightActivationAbilityHookRegistry = field(
        default_factory=FightActivationAbilityHookRegistry.empty
    )
    fight_unit_selected_hooks: FightUnitSelectedHookRegistry = field(
        default_factory=FightUnitSelectedHookRegistry.empty
    )
    fight_unit_selected_grant_hooks: FightUnitSelectedGrantRegistry = field(
        default_factory=FightUnitSelectedGrantRegistry.empty
    )
    attack_sequence_completed_hooks: AttackSequenceCompletedHookRegistry = field(
        default_factory=AttackSequenceCompletedHookRegistry.empty
    )
    fight_phase_start_hooks: FightPhaseStartHookRegistry = field(
        default_factory=FightPhaseStartHookRegistry.empty
    )
    runtime_modifier_registry: RuntimeModifierRegistry = field(
        default_factory=RuntimeModifierRegistry.empty
    )

    def __post_init__(self) -> None:
        if (
            self.ruleset_descriptor is not None
            and type(self.ruleset_descriptor) is not RulesetDescriptor
        ):
            raise GameLifecycleError(
                "FightPhaseHandler ruleset_descriptor must be a RulesetDescriptor."
            )
        if self.army_catalog is not None and type(self.army_catalog) is not ArmyCatalog:
            raise GameLifecycleError("FightPhaseHandler army_catalog must be an ArmyCatalog.")
        if type(self.stratagem_index) is not StratagemCatalogIndex:
            raise GameLifecycleError("FightPhaseHandler stratagem_index must be an index.")
        if type(self.fight_activation_ability_hooks) is not FightActivationAbilityHookRegistry:
            raise GameLifecycleError(
                "FightPhaseHandler fight_activation_ability_hooks must be a registry."
            )
        if type(self.fight_unit_selected_hooks) is not FightUnitSelectedHookRegistry:
            raise GameLifecycleError(
                "FightPhaseHandler fight_unit_selected_hooks must be a registry."
            )
        if type(self.fight_unit_selected_grant_hooks) is not FightUnitSelectedGrantRegistry:
            raise GameLifecycleError(
                "FightPhaseHandler fight_unit_selected_grant_hooks must be a registry."
            )
        if type(self.attack_sequence_completed_hooks) is not AttackSequenceCompletedHookRegistry:
            raise GameLifecycleError(
                "FightPhaseHandler attack_sequence_completed_hooks must be a registry."
            )
        if type(self.fight_phase_start_hooks) is not FightPhaseStartHookRegistry:
            raise GameLifecycleError(
                "FightPhaseHandler fight_phase_start_hooks must be a registry."
            )
        if type(self.runtime_modifier_registry) is not RuntimeModifierRegistry:
            raise GameLifecycleError(
                "FightPhaseHandler runtime_modifier_registry must be a registry."
            )

    @property
    def phase(self) -> BattlePhase:
        return BattlePhase.FIGHT

    def invalid_fight_unit_selected_grant_status(
        self,
        *,
        state: GameState,
        request: DecisionRequest,
        result: DecisionResult,
    ) -> LifecycleStatus | None:
        invalid_status = _invalid_finite_decision_status(
            state=state,
            request=request,
            result=result,
            invalid_reason="invalid_fight_unit_grant_result",
        )
        if invalid_status is not None:
            return invalid_status
        if request.decision_type != SELECT_FIGHT_UNIT_GRANT_DECISION_TYPE:
            raise GameLifecycleError(
                "Fight unit grant prevalidation received unsupported decision_type."
            )
        fight_state = state.fight_phase_state
        if fight_state is None or fight_state.active_activation is None:
            return LifecycleStatus.invalid(
                stage=state.stage,
                message="Fight unit grant has no active activation.",
                payload={
                    "invalid_reason": "invalid_fight_unit_grant_result",
                    "field": "active_activation",
                },
            )
        payload = _decision_payload_object(result.payload)
        try:
            _validate_fight_unit_selected_grant_payload_context(
                payload=payload,
                activation=fight_state.active_activation,
            )
            if result.selected_option_id != DECLINE_FIGHT_UNIT_GRANT_OPTION_ID:
                selected_grants = _selected_fight_unit_grants_from_payload(payload)
                _validate_selected_fight_unit_grants(
                    state=state,
                    activation=fight_state.active_activation,
                    registry=self.fight_unit_selected_grant_hooks,
                    selected_grants=selected_grants,
                )
        except (GameLifecycleError, KeyError, TypeError) as exc:
            return LifecycleStatus.invalid(
                stage=state.stage,
                message=str(exc),
                payload={
                    "invalid_reason": "invalid_fight_unit_grant_result",
                    "field": "payload",
                },
            )
        return None

    def begin_phase(
        self,
        *,
        state: GameState,
        decisions: DecisionController,
        reaction_queue: ReactionQueue | None = None,
    ) -> LifecycleStatus:
        _validate_fight_phase_state(state)
        if state.fight_phase_state is None:
            phase_start_status = _request_fight_phase_start_rule_if_available(
                handler=self,
                state=state,
                decisions=decisions,
            )
            if phase_start_status is not None:
                return phase_start_status
        policy = _fight_policy_for_handler(self)
        fight_state = _ensure_fight_phase_state(
            state=state,
            decisions=decisions,
            policy=policy,
        )
        state.replace_fight_phase_state(fight_state)
        for _iteration in range(64):
            current = _require_fight_state(state)
            if current.phase_complete:
                decisions.event_log.append(
                    "fight_phase_completed",
                    _fight_phase_status_payload(
                        state=state,
                        fight_state=current,
                        phase_body_status=_FIGHT_PHASE_COMPLETE_STATUS,
                    ),
                )
                return LifecycleStatus.advanced(
                    stage=GameLifecycleStage.BATTLE,
                    payload=_fight_phase_status_payload(
                        state=state,
                        fight_state=current,
                        phase_body_status=_FIGHT_PHASE_COMPLETE_STATUS,
                    ),
                )
            status = _advance_fight_phase_body(
                handler=self,
                state=state,
                decisions=decisions,
                reaction_queue=reaction_queue,
                policy=policy,
            )
            if status is not None:
                return status
        raise GameLifecycleError("Fight phase exceeded deterministic Phase 15D guard.")

    def apply_decision(
        self,
        *,
        state: GameState,
        result: DecisionResult,
        decisions: DecisionController,
        reaction_queue: ReactionQueue | None = None,
    ) -> LifecycleStatus | None:
        if result.decision_type == MOVEMENT_PROPOSAL_DECISION_TYPE:
            return _apply_fight_movement_proposal(
                handler=self,
                state=state,
                result=result,
                decisions=decisions,
                policy=_fight_policy_for_handler(self),
            )
        if result.decision_type == SUBMIT_MELEE_DECLARATION_DECISION_TYPE:
            return _apply_melee_declaration_decision(
                handler=self,
                state=state,
                result=result,
                decisions=decisions,
            )
        if result.decision_type in ATTACK_RESOLUTION_SELECTION_DECISION_TYPES:
            _apply_fight_attack_sequence_selection_decision(
                state=state,
                result=result,
                decisions=decisions,
            )
            return None
        if result.decision_type in ATTACK_ALLOCATION_DECISION_TYPES:
            return _apply_fight_attack_sequence_decision(
                handler=self,
                state=state,
                result=result,
                decisions=decisions,
            )
        if result.decision_type == PLACEMENT_PROPOSAL_DECISION_TYPE:
            return _apply_fight_attack_sequence_decision(
                handler=self,
                state=state,
                result=result,
                decisions=decisions,
            )
        if result.decision_type == FIGHT_ACTIVATION_DECISION_TYPE:
            return _apply_fight_activation_decision(
                handler=self,
                state=state,
                result=result,
                decisions=decisions,
                reaction_queue=reaction_queue,
                policy=_fight_policy_for_handler(self),
            )
        if result.decision_type == SELECT_FIGHT_UNIT_GRANT_DECISION_TYPE:
            return _apply_fight_unit_selected_grant_decision(
                state=state,
                result=result,
                decisions=decisions,
                registry=self.fight_unit_selected_grant_hooks,
            )
        if result.decision_type == FIGHT_ACTIVATION_ABILITY_DECISION_TYPE:
            return _apply_fight_activation_ability_decision(
                state=state,
                result=result,
                decisions=decisions,
            )
        if result.decision_type == SELECT_FACTION_RULE_FIGHT_PHASE_START_OPTION_DECISION_TYPE:
            phase_start_result = self.fight_phase_start_hooks.apply_result(
                FightPhaseStartResultContext(
                    state=state,
                    decisions=decisions,
                    request=decisions.record_for_result(result).request,
                    result=result,
                )
            )
            if type(phase_start_result) is LifecycleStatus:
                return phase_start_result
            if phase_start_result:
                return None
            raise GameLifecycleError("Faction rule Fight-phase start decision was not handled.")
        if result.decision_type == FIGHT_INTERRUPT_DECISION_TYPE:
            return _apply_fight_interrupt_decision(
                state=state,
                result=result,
                decisions=decisions,
                policy=_fight_policy_for_handler(self),
            )
        if result.decision_type == DICE_REROLL_DECISION_TYPE:
            return _apply_fight_dice_reroll_decision(
                state=state,
                result=result,
                decisions=decisions,
            )
        raise GameLifecycleError("Fight phase received unsupported decision type.")


def _advance_fight_phase_body(
    *,
    handler: FightPhaseHandler,
    state: GameState,
    decisions: DecisionController,
    reaction_queue: ReactionQueue | None,
    policy: FightPolicyDescriptor,
) -> LifecycleStatus | None:
    fight_state = _require_fight_state(state)
    if fight_state.attack_sequence is not None:
        return _advance_fight_attack_sequence(
            handler=handler,
            state=state,
            decisions=decisions,
            reaction_queue=reaction_queue,
            policy=policy,
        )
    if fight_state.active_activation is not None:
        return _advance_active_fight_activation(
            handler=handler,
            state=state,
            decisions=decisions,
            reaction_queue=reaction_queue,
            policy=policy,
        )
    if fight_state.current_step is FightPhaseStepKind.PILE_IN:
        return _advance_fight_movement_step(
            state=state,
            decisions=decisions,
            policy=policy,
            step=FightPhaseStepKind.PILE_IN,
        )
    if fight_state.current_step is FightPhaseStepKind.FIGHT:
        selected_context = _advance_to_next_fight_request(
            state=state,
            fight_state=fight_state,
            policy=policy,
        )
        if selected_context.fight_state.phase_complete:
            updated_fight_state = selected_context.fight_state.with_current_step(
                current_step=FightPhaseStepKind.CONSOLIDATE,
                policy=policy,
            )
            state.replace_fight_phase_state(updated_fight_state)
            decisions.event_log.append(
                "fight_step_completed",
                _fight_phase_status_payload(
                    state=state,
                    fight_state=updated_fight_state,
                    phase_body_status="fight_step_completed",
                ),
            )
            return None
        state.replace_fight_phase_state(selected_context.fight_state)
        stratagem_status = _request_active_fight_phase_stratagem_if_available(
            handler=handler,
            state=state,
            decisions=decisions,
            fight_state=selected_context.fight_state,
            contexts=selected_context.contexts,
        )
        if stratagem_status is not None:
            return stratagem_status
        return _request_fight_activation(
            state=state,
            decisions=decisions,
            fight_state=selected_context.fight_state,
            contexts=selected_context.contexts,
            pass_available=selected_context.pass_available,
            policy=policy,
        )
    if fight_state.current_step is FightPhaseStepKind.CONSOLIDATE:
        return _advance_fight_movement_step(
            state=state,
            decisions=decisions,
            policy=policy,
            step=FightPhaseStepKind.CONSOLIDATE,
        )
    if fight_state.current_step is FightPhaseStepKind.END:
        state.replace_fight_phase_state(fight_state.with_phase_complete())
        return None
    raise GameLifecycleError("Fight phase body has unsupported current_step.")


def _advance_fight_attack_sequence(
    *,
    handler: FightPhaseHandler,
    state: GameState,
    decisions: DecisionController,
    reaction_queue: ReactionQueue | None,
    policy: FightPolicyDescriptor,
) -> LifecycleStatus | None:
    fight_state = _require_fight_state(state)
    if fight_state.attack_sequence is None:
        raise GameLifecycleError("Fight attack sequence advance requires attack_sequence.")
    attack_sequence, allocated_model_ids, status = resolve_attack_sequence_until_blocked(
        state=state,
        decisions=decisions,
        ruleset_descriptor=_ruleset_descriptor_for_handler(handler),
        attack_sequence=fight_state.attack_sequence,
        already_allocated_model_ids=fight_state.allocated_model_ids_this_phase,
        stratagem_index=handler.stratagem_index,
        runtime_modifier_registry=handler.runtime_modifier_registry,
    )
    updated_state = fight_state.with_attack_sequence_update(
        attack_sequence=attack_sequence,
        allocated_model_ids_this_phase=allocated_model_ids,
    )
    state.replace_fight_phase_state(updated_state)
    if status is not None:
        return status
    activation = updated_state.active_activation
    if activation is None:
        raise GameLifecycleError("Completed melee attack sequence has no active activation.")
    completion_hook_status = handler.attack_sequence_completed_hooks.resolve_completed_sequence(
        AttackSequenceCompletedContext(
            state=state,
            decisions=decisions,
            dice_manager=DiceRollManager(state.game_id, event_log=decisions.event_log),
            runtime_modifier_registry=handler.runtime_modifier_registry,
            source_phase=BattlePhase.FIGHT,
            attack_sequence=fight_state.attack_sequence,
            attack_sequence_completed_event_id=attack_sequence_completed_event_id(
                decisions=decisions,
                attack_sequence=fight_state.attack_sequence,
            ),
        )
    )
    if completion_hook_status is not None:
        return completion_hook_status
    decisions.event_log.append(
        "melee_attack_sequence_completed",
        validate_json_value(
            {
                "game_id": state.game_id,
                "battle_round": state.battle_round,
                "phase": BattlePhase.FIGHT.value,
                "phase_body_status": "melee_attack_sequence_completed",
                "activation_selection": activation.to_payload(),
            }
        ),
    )
    return _complete_active_fight_activation(
        handler=handler,
        state=state,
        decisions=decisions,
        reaction_queue=reaction_queue,
        policy=policy,
        activation=activation,
    )


def _advance_active_fight_activation(
    *,
    handler: FightPhaseHandler,
    state: GameState,
    decisions: DecisionController,
    reaction_queue: ReactionQueue | None,
    policy: FightPolicyDescriptor,
) -> LifecycleStatus | None:
    fight_state = _require_fight_state(state)
    activation = fight_state.active_activation
    if activation is None:
        raise GameLifecycleError("Active fight activation advance requires selection.")
    if (
        activation.fight_type is FightTypeKind.OVERRUN
        and not fight_state.overrun_pile_in_is_completed(
            activation_result_id=activation.result_id,
        )
    ):
        return _request_overrun_pile_in(
            state=state,
            decisions=decisions,
            activation=activation,
        )
    scenario = _battlefield_scenario(state)
    target_ids = melee_target_unit_ids(
        scenario=scenario,
        ruleset_descriptor=_ruleset_descriptor_for_handler(handler),
        unit_instance_id=activation.unit_instance_id,
    )
    unit = _unit_by_id(state=state, unit_instance_id=activation.unit_instance_id)
    available_weapons = available_melee_weapons_payloads(
        scenario=scenario,
        ruleset_descriptor=_ruleset_descriptor_for_handler(handler),
        unit=unit,
        army_catalog=_army_catalog_for_handler(handler),
        state=state,
        source_decision_result_id=activation.result_id,
    )
    if not target_ids or not available_weapons:
        decisions.event_log.append(
            "melee_declaration_not_available",
            validate_json_value(
                {
                    "game_id": state.game_id,
                    "battle_round": state.battle_round,
                    "phase": BattlePhase.FIGHT.value,
                    "phase_body_status": "melee_declaration_not_available",
                    "activation_selection": activation.to_payload(),
                    "target_unit_instance_ids": list(target_ids),
                    "available_weapon_count": len(available_weapons),
                }
            ),
        )
        return _complete_active_fight_activation(
            handler=handler,
            state=state,
            decisions=decisions,
            reaction_queue=reaction_queue,
            policy=policy,
            activation=activation,
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
    request = build_melee_declaration_request(
        request_id=state.next_decision_request_id(),
        game_id=state.game_id,
        battle_round=state.battle_round,
        active_player_id=fight_state.active_player_id,
        actor_id=activation.player_id,
        unit_instance_id=activation.unit_instance_id,
        source_decision_request_id=activation.request_id,
        source_decision_result_id=activation.result_id,
        ruleset_descriptor=_ruleset_descriptor_for_handler(handler),
        available_weapons=available_weapons,
        target_unit_instance_ids=target_ids,
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
            "unit_instance_id": activation.unit_instance_id,
            "proposal_kind": MELEE_DECLARATION_PROPOSAL_KIND,
        },
    )


def _complete_active_fight_activation(
    *,
    handler: FightPhaseHandler,
    state: GameState,
    decisions: DecisionController,
    reaction_queue: ReactionQueue | None,
    policy: FightPolicyDescriptor,
    activation: FightActivationSelection,
) -> LifecycleStatus | None:
    fight_state = _require_fight_state(state)
    state.replace_fight_phase_state(fight_state.with_active_activation(None))
    event = decisions.event_log.append(
        "unit_has_fought",
        validate_json_value(
            {
                "game_id": state.game_id,
                "battle_round": state.battle_round,
                "phase": BattlePhase.FIGHT.value,
                "phase_body_status": _UNIT_FOUGHT_STATUS,
                "activation_selection": activation.to_payload(),
            }
        ),
    )
    counteroffensive_status = _request_counteroffensive_if_available(
        handler=handler,
        state=state,
        decisions=decisions,
        reaction_queue=reaction_queue,
        fought_selection=activation,
        trigger_event_id=event.event_id,
        policy=policy,
    )
    if counteroffensive_status is not None:
        return counteroffensive_status
    return _request_fight_interrupt_if_available(
        state=state,
        decisions=decisions,
        reaction_queue=reaction_queue,
        fought_selection=activation,
        trigger_event_id=event.event_id,
        policy=policy,
    )


def _request_fight_activation_ability_if_available(
    *,
    handler: FightPhaseHandler,
    state: GameState,
    decisions: DecisionController,
    fight_state: FightPhaseState,
    activation: FightActivationSelection,
    target_unit_instance_ids: tuple[str, ...],
) -> LifecycleStatus | None:
    if _fight_activation_ability_window_resolved(
        state=state,
        decisions=decisions,
        activation=activation,
    ):
        return None
    context = FightActivationAbilityContext(
        state=state,
        game_id=state.game_id,
        battle_round=state.battle_round,
        active_player_id=fight_state.active_player_id,
        player_id=activation.player_id,
        unit_instance_id=activation.unit_instance_id,
        activation=activation,
        target_unit_instance_ids=target_unit_instance_ids,
    )
    ability_options = handler.fight_activation_ability_hooks.options_for(context)
    if not ability_options:
        return None
    request = build_fight_activation_ability_request(
        request_id=state.next_decision_request_id(),
        game_id=state.game_id,
        context=context,
        ability_options=ability_options,
    )
    decisions.request_decision(request)
    decisions.event_log.append(
        "fight_activation_ability_requested",
        validate_json_value(
            {
                "game_id": state.game_id,
                "battle_round": state.battle_round,
                "phase": BattlePhase.FIGHT.value,
                "phase_body_status": _FIGHT_ACTIVATION_ABILITY_REQUIRED_STATUS,
                "request_id": request.request_id,
                "activation_selection": activation.to_payload(),
                "ability_option_ids": [option.option_id for option in ability_options],
                "target_unit_instance_ids": list(target_unit_instance_ids),
            }
        ),
    )
    return LifecycleStatus.waiting_for_decision(
        stage=GameLifecycleStage.BATTLE,
        decision_request=request,
        payload={
            "phase": BattlePhase.FIGHT.value,
            "phase_body_status": _FIGHT_ACTIVATION_ABILITY_REQUIRED_STATUS,
            "unit_instance_id": activation.unit_instance_id,
            "activation_result_id": activation.result_id,
        },
    )


def _fight_activation_ability_window_resolved(
    *,
    state: GameState,
    decisions: DecisionController,
    activation: FightActivationSelection,
) -> bool:
    for effect in state.persisting_effects:
        if activation.unit_instance_id not in effect.target_unit_instance_ids:
            continue
        effect_payload = effect.effect_payload
        if not isinstance(effect_payload, dict):
            continue
        if effect_payload.get("effect_kind") not in FIGHT_ACTIVATION_ABILITY_EFFECT_KINDS:
            continue
        if effect_payload.get("activation_result_id") == activation.result_id:
            return True
    for event in decisions.event_log.records:
        if event.event_type not in {
            "fight_activation_ability_declined",
            "fight_activation_ability_used",
        }:
            continue
        payload = event.payload
        if not isinstance(payload, dict):
            continue
        if payload.get("activation_result_id") == activation.result_id:
            return True
    return False


def _advance_fight_movement_step(
    *,
    state: GameState,
    decisions: DecisionController,
    policy: FightPolicyDescriptor,
    step: FightPhaseStepKind,
) -> LifecycleStatus | None:
    fight_state = _require_fight_state(state)
    movement_state = _movement_step_state(fight_state=fight_state, step=step)
    eligible_unit_ids = _eligible_fight_movement_unit_ids(
        state=state,
        fight_state=fight_state,
        policy=policy,
        step=step,
        player_id=movement_state.next_player_id,
    )
    remaining_unit_ids = tuple(
        unit_id for unit_id in eligible_unit_ids if unit_id not in movement_state.completed_unit_ids
    )
    if remaining_unit_ids:
        return _request_fight_movement(
            state=state,
            decisions=decisions,
            fight_state=fight_state,
            movement_state=movement_state,
            unit_instance_id=remaining_unit_ids[0],
        )
    if movement_state.next_player_id not in movement_state.completed_player_ids:
        next_player_id = _next_player_id(
            player_ids=state.player_ids,
            current_player_id=movement_state.next_player_id,
        )
        updated_movement_state = movement_state.with_completed_player(next_player_id=next_player_id)
        state.replace_fight_phase_state(
            _with_movement_step_state(
                fight_state=fight_state,
                movement_state=updated_movement_state,
            )
        )
        return None
    if step is FightPhaseStepKind.PILE_IN:
        updated_fight_state = fight_state.with_current_step(
            current_step=FightPhaseStepKind.FIGHT,
            policy=policy,
        )
        state.replace_fight_phase_state(updated_fight_state)
        decisions.event_log.append(
            "pile_in_step_completed",
            _fight_phase_status_payload(
                state=state,
                fight_state=updated_fight_state,
                phase_body_status="pile_in_step_completed",
            ),
        )
        return None
    if step is FightPhaseStepKind.CONSOLIDATE:
        updated_fight_state = fight_state.with_current_step(
            current_step=FightPhaseStepKind.END,
            policy=policy,
        )
        state.replace_fight_phase_state(updated_fight_state)
        decisions.event_log.append(
            "consolidate_step_completed",
            _fight_phase_status_payload(
                state=state,
                fight_state=updated_fight_state,
                phase_body_status="consolidate_step_completed",
            ),
        )
        return None
    raise GameLifecycleError("Unsupported fight movement step.")


def _request_fight_movement(
    *,
    state: GameState,
    decisions: DecisionController,
    fight_state: FightPhaseState,
    movement_state: FightMovementStepState,
    unit_instance_id: str,
) -> LifecycleStatus:
    proposal_kind = _proposal_kind_for_fight_step(movement_state.step)
    context = _fight_movement_request_context(
        state=state,
        fight_state=fight_state,
        movement_state=movement_state,
        unit_instance_id=unit_instance_id,
    )
    request = build_fight_movement_request(
        state_game_id=state.game_id,
        battle_round=state.battle_round,
        active_player_id=fight_state.active_player_id,
        request_id=state.next_decision_request_id(),
        actor_id=movement_state.next_player_id,
        unit_instance_id=unit_instance_id,
        proposal_kind=proposal_kind,
        source_decision_request_id=(
            f"fight-step:{state.battle_round}:{movement_state.step.value}:request"
        ),
        source_decision_result_id=(
            f"fight-step:{state.battle_round}:{movement_state.step.value}:result"
        ),
        context=context,
    )
    decisions.request_decision(request)
    phase_body_status = (
        _FIGHT_PILE_IN_REQUIRED_STATUS
        if movement_state.step is FightPhaseStepKind.PILE_IN
        else _FIGHT_CONSOLIDATE_REQUIRED_STATUS
    )
    decisions.event_log.append(
        "fight_movement_requested",
        validate_json_value(
            {
                "game_id": state.game_id,
                "battle_round": state.battle_round,
                "phase": BattlePhase.FIGHT.value,
                "phase_body_status": phase_body_status,
                "request_id": request.request_id,
                "player_id": movement_state.next_player_id,
                "unit_instance_id": unit_instance_id,
                "proposal_kind": proposal_kind.value,
                "context": context,
            }
        ),
    )
    return LifecycleStatus.waiting_for_decision(
        stage=GameLifecycleStage.BATTLE,
        decision_request=request,
        payload={
            "phase": BattlePhase.FIGHT.value,
            "phase_body_status": phase_body_status,
            "unit_instance_id": unit_instance_id,
            "proposal_kind": proposal_kind.value,
        },
    )


def _request_overrun_pile_in(
    *,
    state: GameState,
    decisions: DecisionController,
    activation: FightActivationSelection,
) -> LifecycleStatus:
    fight_state = _require_fight_state(state)
    context = _fight_movement_request_context(
        state=state,
        fight_state=fight_state,
        movement_state=FightMovementStepState.start(
            step=FightPhaseStepKind.PILE_IN,
            next_player_id=activation.player_id,
        ),
        unit_instance_id=activation.unit_instance_id,
    )
    context["fight_movement_timing"] = "overrun"
    request = build_fight_movement_request(
        state_game_id=state.game_id,
        battle_round=state.battle_round,
        active_player_id=fight_state.active_player_id,
        request_id=state.next_decision_request_id(),
        actor_id=activation.player_id,
        unit_instance_id=activation.unit_instance_id,
        proposal_kind=ProposalKind.PILE_IN,
        source_decision_request_id=activation.request_id,
        source_decision_result_id=activation.result_id,
        context=context,
    )
    decisions.request_decision(request)
    decisions.event_log.append(
        "overrun_pile_in_requested",
        validate_json_value(
            {
                "game_id": state.game_id,
                "battle_round": state.battle_round,
                "phase": BattlePhase.FIGHT.value,
                "phase_body_status": _FIGHT_PILE_IN_REQUIRED_STATUS,
                "request_id": request.request_id,
                "activation_selection": activation.to_payload(),
                "proposal_kind": ProposalKind.PILE_IN.value,
            }
        ),
    )
    return LifecycleStatus.waiting_for_decision(
        stage=GameLifecycleStage.BATTLE,
        decision_request=request,
        payload={
            "phase": BattlePhase.FIGHT.value,
            "phase_body_status": _FIGHT_PILE_IN_REQUIRED_STATUS,
            "unit_instance_id": activation.unit_instance_id,
            "proposal_kind": ProposalKind.PILE_IN.value,
        },
    )


def _request_fight_movement_proposal_retry(
    *,
    state: GameState,
    decisions: DecisionController,
    proposal_request: MovementProposalRequest,
    rejected_result: DecisionResult,
) -> DecisionRequest:
    if proposal_request.movement_phase_action is None:
        raise GameLifecycleError("Fight movement retry requires movement_phase_action.")
    context = dict(proposal_request.context or {})
    retry_proposal = MovementProposalRequest(
        request_id=state.next_decision_request_id(),
        decision_type=MOVEMENT_PROPOSAL_DECISION_TYPE,
        actor_id=proposal_request.actor_id,
        game_id=state.game_id,
        battle_round=state.battle_round,
        phase=BattlePhase.FIGHT.value,
        unit_instance_id=proposal_request.unit_instance_id,
        proposal_kind=proposal_request.proposal_kind,
        source_decision_request_id=proposal_request.source_decision_request_id,
        source_decision_result_id=proposal_request.source_decision_result_id,
        movement_phase_action=proposal_request.movement_phase_action,
        context=context,
    )
    request = retry_proposal.to_decision_request()
    decisions.request_decision(request)
    decisions.event_log.append(
        "fight_movement_requested",
        validate_json_value(
            {
                "game_id": state.game_id,
                "battle_round": state.battle_round,
                "phase": BattlePhase.FIGHT.value,
                "phase_body_status": _fight_movement_required_status(
                    proposal_request.proposal_kind
                ),
                "request_id": request.request_id,
                "player_id": proposal_request.actor_id,
                "unit_instance_id": proposal_request.unit_instance_id,
                "proposal_kind": proposal_request.proposal_kind.value,
                "movement_phase_action": proposal_request.movement_phase_action,
                "movement_mode": _payload_string(context, key="movement_mode"),
                "source_decision_request_id": proposal_request.source_decision_request_id,
                "source_decision_result_id": proposal_request.source_decision_result_id,
                "previous_proposal_request_id": proposal_request.request_id,
                "rejected_result_id": rejected_result.result_id,
                "context": context,
            }
        ),
    )
    return request


def _fight_movement_required_status(proposal_kind: ProposalKind) -> str:
    if proposal_kind is ProposalKind.PILE_IN:
        return _FIGHT_PILE_IN_REQUIRED_STATUS
    if proposal_kind is ProposalKind.CONSOLIDATE:
        return _FIGHT_CONSOLIDATE_REQUIRED_STATUS
    raise GameLifecycleError("Proposal kind is not a fight movement step.")


def invalid_fight_movement_proposal_status(
    *,
    state: GameState,
    request: DecisionRequest,
    result: DecisionResult,
    ruleset_descriptor: RulesetDescriptor,
    decisions: DecisionController,
) -> LifecycleStatus | None:
    proposal_request = MovementProposalRequest.from_decision_request_payload(request.payload)
    parsed = _parse_fight_movement_proposal_or_invalid(
        state=state,
        proposal_request=proposal_request,
        result=result,
    )
    if isinstance(parsed, LifecycleStatus):
        return parsed
    proposal = parsed
    proposal_validation = proposal.validation_result_for_request(proposal_request)
    if not proposal_validation.is_valid and not _proposal_validation_has_code(
        proposal_validation,
        _ENDPOINT_ONLY_PATH_VIOLATION_CODE,
    ):
        return _reject_invalid_fight_proposal(
            state=state,
            proposal_validation=proposal_validation,
            message="Fight movement proposal does not match the pending request.",
        )
    rule_validation = fight_movement_rule_validation(
        scenario=_battlefield_scenario(state),
        ruleset_descriptor=ruleset_descriptor,
        proposal_request=proposal_request,
        proposal=proposal,
        eligible_unit_ids=_eligible_fight_movement_unit_ids_for_request(
            state=state,
            proposal_request=proposal_request,
            ruleset_descriptor=ruleset_descriptor,
        ),
    )
    if not rule_validation.is_valid:
        return _reject_invalid_fight_proposal(
            state=state,
            proposal_validation=rule_validation,
            message="Fight movement proposal is not currently legal.",
        )
    witness_validation = _fight_movement_witness_matches_current_unit_status(
        state=state,
        proposal_request=proposal_request,
        proposal=proposal,
    )
    if witness_validation is not None:
        return _reject_invalid_fight_proposal(
            state=state,
            proposal_validation=witness_validation,
            message="Fight movement witness does not match the current unit.",
        )
    del decisions
    return None


def invalid_melee_declaration_status(
    *,
    state: GameState,
    request: DecisionRequest,
    result: DecisionResult,
    ruleset_descriptor: RulesetDescriptor,
    army_catalog: ArmyCatalog,
) -> LifecycleStatus | None:
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
    rule_validation = validate_melee_declaration_rules(
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


def invalid_fight_attack_sequence_selection_status(
    *,
    state: GameState,
    request: DecisionRequest,
    result: DecisionResult,
) -> LifecycleStatus | None:
    if request.decision_type not in ATTACK_RESOLUTION_SELECTION_DECISION_TYPES:
        raise GameLifecycleError(
            "Fight attack sequence selection prevalidation received unsupported decision_type."
        )
    try:
        result.validate_for_request(request)
    except DecisionError as exc:
        return LifecycleStatus.invalid(
            stage=state.stage,
            message="Fight attack sequence selection result is malformed.",
            payload={
                "invalid_reason": "fight_attack_sequence_selection_malformed",
                "detail": str(exc),
            },
        )
    attack_sequence = _fight_attack_sequence_for_request(state=state, request=request)
    if request.decision_type == SELECT_RESOLVE_TARGET_UNIT_DECISION_TYPE:
        selected_target_id = selected_resolve_target_from_result(result)
        if selected_target_id not in unresolved_target_unit_ids(attack_sequence):
            return LifecycleStatus.invalid(
                stage=state.stage,
                message="Fight resolve target selection is no longer legal.",
                payload={
                    "invalid_reason": "fight_resolve_target_option_drift",
                    "selected_target_unit_instance_id": selected_target_id,
                },
            )
        expected_request = build_select_resolve_target_unit_request(
            request_id=request.request_id,
            state=state,
            attack_sequence=attack_sequence,
        )
        return _invalid_if_current_option_payload_drifted(
            state=state,
            result=result,
            expected_request=expected_request,
            invalid_reason="fight_resolve_target_payload_drift",
        )
    selected_group = selected_attack_weapon_group_from_result(result)
    if attack_sequence.selected_target_unit_instance_id != selected_group.target_unit_instance_id:
        return LifecycleStatus.invalid(
            stage=state.stage,
            message="Fight attack weapon group target context drifted.",
            payload={
                "invalid_reason": "fight_attack_group_target_drift",
                "selected_target_unit_instance_id": selected_group.target_unit_instance_id,
            },
        )
    current_groups = gathered_attack_groups_for_target(
        attack_sequence=attack_sequence,
        target_unit_instance_id=selected_group.target_unit_instance_id,
    )
    if selected_group.group_id not in {group.group_id for group in current_groups}:
        return LifecycleStatus.invalid(
            stage=state.stage,
            message="Fight attack weapon group selection is no longer legal.",
            payload={
                "invalid_reason": "fight_attack_group_option_drift",
                "selected_group_id": selected_group.group_id,
            },
        )
    expected_request = build_select_attack_weapon_group_request(
        request_id=request.request_id,
        state=state,
        attack_sequence=attack_sequence,
        target_unit_instance_id=selected_group.target_unit_instance_id,
    )
    return _invalid_if_current_option_payload_drifted(
        state=state,
        result=result,
        expected_request=expected_request,
        invalid_reason="fight_attack_group_payload_drift",
    )


def _apply_fight_movement_proposal(
    *,
    handler: FightPhaseHandler,
    state: GameState,
    result: DecisionResult,
    decisions: DecisionController,
    policy: FightPolicyDescriptor,
) -> LifecycleStatus | None:
    del handler
    record = decisions.record_for_result(result)
    proposal_request = MovementProposalRequest.from_decision_request_payload(record.request.payload)
    proposal = fight_movement_proposal_from_payload(result.payload)
    proposal_validation = proposal.validation_result_for_request(proposal_request)
    if not proposal_validation.is_valid:
        if not _proposal_validation_has_code(
            proposal_validation,
            _ENDPOINT_ONLY_PATH_VIOLATION_CODE,
        ):
            raise GameLifecycleError("Recorded fight movement proposal drifted before application.")
        return _reject_recorded_invalid_fight_movement(
            state=state,
            decisions=decisions,
            result=result,
            proposal_request=proposal_request,
            proposal_validation=proposal_validation,
            resolution=None,
            message="Fight movement PathWitness must not repeat only endpoint poses.",
        )
    scenario = _battlefield_scenario(state)
    ruleset_descriptor = state.runtime_ruleset_descriptor()
    resolution = resolve_fight_movement(
        scenario=scenario,
        ruleset_descriptor=ruleset_descriptor,
        proposal=proposal,
        maximum_distance_inches=fight_movement_maximum_distance_inches(
            state=state,
            unit_instance_id=proposal.unit_instance_id,
            proposal_kind=proposal.proposal_kind,
        ),
    )
    resolution_violation = fight_movement_resolution_violation(
        proposal_request=proposal_request,
        proposal=proposal,
        resolution=resolution,
        scenario=scenario,
        ruleset_descriptor=state.runtime_ruleset_descriptor(),
    )
    if resolution_violation is not None:
        violation_code = _first_proposal_violation_code(resolution_violation)
        return _reject_recorded_invalid_fight_movement(
            state=state,
            decisions=decisions,
            result=result,
            proposal_request=proposal_request,
            proposal_validation=resolution_violation,
            resolution=resolution,
            message=_fight_movement_invalid_message(violation_code),
        )
    battlefield_state = state.battlefield_state
    if battlefield_state is None:
        raise GameLifecycleError("Fight movement requires battlefield_state.")
    before = battlefield_state.unit_placement_by_id(proposal.unit_instance_id)
    transition_batch = resolution.transition_batch(before=before)
    state.replace_battlefield_state(
        battlefield_state.with_unit_placement(resolution.attempted_placement)
    )
    fight_state = _require_fight_state(state)
    if _is_overrun_movement_request(proposal_request):
        activation = fight_state.active_activation
        if activation is None:
            raise GameLifecycleError("Overrun pile-in application requires active activation.")
        state.replace_fight_phase_state(
            fight_state.with_overrun_pile_in_completed(
                activation_result_id=activation.result_id,
            )
        )
    else:
        movement_state = _movement_step_state(
            fight_state=fight_state,
            step=_fight_step_for_proposal_kind(proposal.proposal_kind),
        ).with_completed_unit(unit_instance_id=proposal.unit_instance_id)
        state.replace_fight_phase_state(
            _with_movement_step_state(
                fight_state=fight_state,
                movement_state=movement_state,
            )
        )
    decisions.event_log.append(
        "fight_movement_completed",
        validate_json_value(
            {
                "game_id": state.game_id,
                "battle_round": state.battle_round,
                "phase": BattlePhase.FIGHT.value,
                "phase_body_status": _FIGHT_MOVEMENT_COMPLETED_STATUS,
                "request_id": result.request_id,
                "result_id": result.result_id,
                "proposal_request_id": proposal_request.request_id,
                "proposal_kind": proposal.proposal_kind.value,
                "unit_instance_id": proposal.unit_instance_id,
                "transition_batch": transition_batch.to_payload(),
                "resolution": resolution.to_payload(),
            }
        ),
    )
    return None


def _apply_melee_declaration_decision(
    *,
    handler: FightPhaseHandler,
    state: GameState,
    result: DecisionResult,
    decisions: DecisionController,
) -> LifecycleStatus | None:
    record = decisions.record_for_result(result)
    proposal_request = MeleeDeclarationProposalRequest.from_decision_request(record.request)
    proposal = melee_declaration_proposal_from_payload(result.payload)
    sequence_id = (
        f"melee-sequence:{state.game_id}:round-{state.battle_round:02d}:"
        f"{proposal.unit_instance_id}:{result.result_id}"
    )
    attack_sequence = melee_attack_sequence_from_proposal(
        scenario=_battlefield_scenario(state),
        ruleset_descriptor=_ruleset_descriptor_for_handler(handler),
        proposal=proposal,
        army_catalog=_army_catalog_for_handler(handler),
        dice_manager=DiceRollManager(state.game_id, event_log=decisions.event_log),
        sequence_id=sequence_id,
        state=state,
        runtime_modifier_registry=handler.runtime_modifier_registry,
    )
    one_shot_records = record_one_shot_melee_weapon_uses(
        state=state,
        scenario=_battlefield_scenario(state),
        proposal=proposal,
        army_catalog=_army_catalog_for_handler(handler),
        result_id=result.result_id,
    )
    fight_state = _require_fight_state(state)
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
                "one_shot_weapon_use_records": [record.to_payload() for record in one_shot_records],
            }
        ),
    )
    return None


def _apply_fight_attack_sequence_selection_decision(
    *,
    state: GameState,
    result: DecisionResult,
    decisions: DecisionController,
) -> None:
    fight_state = _require_fight_state(state)
    if fight_state.attack_sequence is None:
        raise GameLifecycleError("Fight attack sequence selection requires attack_sequence.")
    if result.decision_type == SELECT_RESOLVE_TARGET_UNIT_DECISION_TYPE:
        attack_sequence = apply_resolve_target_unit_decision(
            decisions=decisions,
            attack_sequence=fight_state.attack_sequence,
            result=result,
        )
    elif result.decision_type == SELECT_ATTACK_WEAPON_GROUP_DECISION_TYPE:
        attack_sequence = apply_attack_weapon_group_decision(
            decisions=decisions,
            attack_sequence=fight_state.attack_sequence,
            result=result,
        )
    else:
        raise GameLifecycleError("Unsupported fight attack sequence selection decision type.")
    state.replace_fight_phase_state(
        fight_state.with_attack_sequence_update(
            attack_sequence=attack_sequence,
            allocated_model_ids_this_phase=fight_state.allocated_model_ids_this_phase,
        )
    )


def _apply_fight_attack_sequence_decision(
    *,
    handler: FightPhaseHandler,
    state: GameState,
    result: DecisionResult,
    decisions: DecisionController,
) -> LifecycleStatus | None:
    fight_state = _require_fight_state(state)
    if fight_state.attack_sequence is None:
        raise GameLifecycleError("Fight attack sequence decision requires attack_sequence.")
    updated_sequence: AttackSequence | None
    allocated_model_ids: tuple[str, ...]
    status: LifecycleStatus | None
    if result.decision_type == SELECT_PSYCHIC_ATTACK_MODIFIER_IGNORES_DECISION_TYPE:
        validate_psychic_attack_modifier_ignore_decision(
            decisions=decisions,
            attack_sequence=fight_state.attack_sequence,
            result=result,
        )
        updated_sequence = fight_state.attack_sequence
        allocated_model_ids = fight_state.allocated_model_ids_this_phase
        status = None
    elif result.decision_type == SELECT_ALLOCATION_ORDER_DECISION_TYPE:
        updated_sequence, allocated_model_ids, status = apply_allocation_order_decision(
            state=state,
            decisions=decisions,
            ruleset_descriptor=_ruleset_descriptor_for_handler(handler),
            attack_sequence=fight_state.attack_sequence,
            result=result,
            already_allocated_model_ids=fight_state.allocated_model_ids_this_phase,
            stratagem_index=handler.stratagem_index,
        )
    elif result.decision_type == SELECT_DAMAGE_ALLOCATION_MODEL_DECISION_TYPE:
        updated_sequence, allocated_model_ids, status = apply_damage_allocation_model_decision(
            state=state,
            decisions=decisions,
            ruleset_descriptor=_ruleset_descriptor_for_handler(handler),
            attack_sequence=fight_state.attack_sequence,
            result=result,
            already_allocated_model_ids=fight_state.allocated_model_ids_this_phase,
            stratagem_index=handler.stratagem_index,
        )
    elif result.decision_type == SELECT_PRECISION_ALLOCATION_DECISION_TYPE:
        updated_sequence, allocated_model_ids, status = apply_precision_allocation_decision(
            state=state,
            decisions=decisions,
            ruleset_descriptor=_ruleset_descriptor_for_handler(handler),
            attack_sequence=fight_state.attack_sequence,
            result=result,
            already_allocated_model_ids=fight_state.allocated_model_ids_this_phase,
            stratagem_index=handler.stratagem_index,
        )
    elif result.decision_type == SELECT_FEEL_NO_PAIN_DECISION_TYPE:
        updated_sequence, allocated_model_ids, status = apply_feel_no_pain_decision(
            state=state,
            decisions=decisions,
            ruleset_descriptor=_ruleset_descriptor_for_handler(handler),
            attack_sequence=fight_state.attack_sequence,
            result=result,
            already_allocated_model_ids=fight_state.allocated_model_ids_this_phase,
        )
    elif result.decision_type == SELECT_DESTRUCTION_REACTION_DECISION_TYPE:
        updated_sequence, allocated_model_ids, status = apply_destruction_reaction_decision(
            state=state,
            decisions=decisions,
            ruleset_descriptor=_ruleset_descriptor_for_handler(handler),
            attack_sequence=fight_state.attack_sequence,
            result=result,
            already_allocated_model_ids=fight_state.allocated_model_ids_this_phase,
        )
    elif (
        result.decision_type == PLACEMENT_PROPOSAL_DECISION_TYPE
        and is_destroyed_transport_disembark_proposal_request(
            decisions.record_for_result(result).request
        )
    ):
        updated_sequence, allocated_model_ids, status = (
            apply_destroyed_transport_disembark_proposal_decision(
                state=state,
                decisions=decisions,
                ruleset_descriptor=_ruleset_descriptor_for_handler(handler),
                attack_sequence=fight_state.attack_sequence,
                result=result,
                already_allocated_model_ids=fight_state.allocated_model_ids_this_phase,
            )
        )
    else:
        raise GameLifecycleError("Unsupported fight attack sequence decision type.")
    state.replace_fight_phase_state(
        fight_state.with_attack_sequence_update(
            attack_sequence=updated_sequence,
            allocated_model_ids_this_phase=allocated_model_ids,
        )
    )
    return status


def _movement_step_state(
    *,
    fight_state: FightPhaseState,
    step: FightPhaseStepKind,
) -> FightMovementStepState:
    if step is FightPhaseStepKind.PILE_IN:
        if fight_state.pile_in_state is None:
            raise GameLifecycleError("Fight phase missing pile_in_state.")
        return fight_state.pile_in_state
    if step is FightPhaseStepKind.CONSOLIDATE:
        if fight_state.consolidate_state is None:
            raise GameLifecycleError("Fight phase missing consolidate_state.")
        return fight_state.consolidate_state
    raise GameLifecycleError("Fight movement step must be Pile In or Consolidate.")


def _with_movement_step_state(
    *,
    fight_state: FightPhaseState,
    movement_state: FightMovementStepState,
) -> FightPhaseState:
    if movement_state.step is FightPhaseStepKind.PILE_IN:
        return fight_state.with_pile_in_state(movement_state)
    if movement_state.step is FightPhaseStepKind.CONSOLIDATE:
        return fight_state.with_consolidate_state(movement_state)
    raise GameLifecycleError("Fight movement state has unsupported step.")


def _proposal_kind_for_fight_step(step: FightPhaseStepKind) -> ProposalKind:
    if step is FightPhaseStepKind.PILE_IN:
        return ProposalKind.PILE_IN
    if step is FightPhaseStepKind.CONSOLIDATE:
        return ProposalKind.CONSOLIDATE
    raise GameLifecycleError("Fight movement step has no proposal kind.")


def _fight_step_for_proposal_kind(proposal_kind: ProposalKind) -> FightPhaseStepKind:
    if proposal_kind is ProposalKind.PILE_IN:
        return FightPhaseStepKind.PILE_IN
    if proposal_kind is ProposalKind.CONSOLIDATE:
        return FightPhaseStepKind.CONSOLIDATE
    raise GameLifecycleError("Proposal kind is not a fight movement step.")


def _fight_movement_request_context(
    *,
    state: GameState,
    fight_state: FightPhaseState,
    movement_state: FightMovementStepState,
    unit_instance_id: str,
) -> dict[str, JsonValue]:
    scenario = _battlefield_scenario(state)
    if movement_state.step is FightPhaseStepKind.PILE_IN:
        maximum_distance_inches = fight_movement_maximum_distance_inches(
            state=state,
            unit_instance_id=unit_instance_id,
            proposal_kind=ProposalKind.PILE_IN,
        )
        return {
            "fight_movement_step": movement_state.step.value,
            "movement_mode": "pile_in",
            "maximum_distance_inches": maximum_distance_inches,
            "eligible_unit_ids": list(
                _eligible_fight_movement_unit_ids(
                    state=state,
                    fight_state=fight_state,
                    policy=state.runtime_ruleset_descriptor().fight_policy,
                    step=movement_state.step,
                    player_id=movement_state.next_player_id,
                )
            ),
            "legal_target_unit_instance_ids": list(
                legal_pile_in_target_unit_ids(
                    scenario=scenario,
                    ruleset_descriptor=state.runtime_ruleset_descriptor(),
                    unit_instance_id=unit_instance_id,
                )
            ),
        }
    objective_markers = _objective_markers_for_state(state)
    maximum_distance_inches = fight_movement_maximum_distance_inches(
        state=state,
        unit_instance_id=unit_instance_id,
        proposal_kind=ProposalKind.CONSOLIDATE,
    )
    return {
        "fight_movement_step": movement_state.step.value,
        "movement_mode": "consolidate",
        "maximum_distance_inches": maximum_distance_inches,
        "eligible_unit_ids": list(
            _eligible_fight_movement_unit_ids(
                state=state,
                fight_state=fight_state,
                policy=state.runtime_ruleset_descriptor().fight_policy,
                step=movement_state.step,
                player_id=movement_state.next_player_id,
            )
        ),
        "legal_consolidation_modes": [
            mode.value
            for mode in legal_consolidation_modes(
                scenario=scenario,
                ruleset_descriptor=state.runtime_ruleset_descriptor(),
                unit_instance_id=unit_instance_id,
                objective_markers=objective_markers,
            )
        ],
        "objective_markers": [
            validate_json_value(marker.to_payload()) for marker in objective_markers
        ],
    }


def _eligible_fight_movement_unit_ids(
    *,
    state: GameState,
    fight_state: FightPhaseState,
    policy: FightPolicyDescriptor,
    step: FightPhaseStepKind,
    player_id: str,
) -> tuple[str, ...]:
    scenario = _battlefield_scenario(state)
    unit_ids = _unit_ids_for_player(state=state, player_id=player_id)
    eligible: list[str] = []
    for unit_id in unit_ids:
        if step is FightPhaseStepKind.PILE_IN:
            if (
                unit_id
                not in fight_state.fight_order_state.fights_first_registry.charged_unit_ids()
                and not melee_target_unit_ids(
                    scenario=scenario,
                    ruleset_descriptor=state.runtime_ruleset_descriptor(),
                    unit_instance_id=unit_id,
                )
            ):
                continue
            if not legal_pile_in_target_unit_ids(
                scenario=scenario,
                ruleset_descriptor=state.runtime_ruleset_descriptor(),
                unit_instance_id=unit_id,
            ):
                continue
            eligible.append(unit_id)
            continue
        if step is FightPhaseStepKind.CONSOLIDATE:
            was_eligible = (
                unit_id in fight_state.fight_order_state.selected_to_fight_unit_ids
                or unit_id in fight_state.fight_order_state.fights_first_registry.charged_unit_ids()
                or unit_id in fight_state.fight_order_state.engaged_at_fight_step_start_unit_ids
                or bool(
                    melee_target_unit_ids(
                        scenario=scenario,
                        ruleset_descriptor=state.runtime_ruleset_descriptor(),
                        unit_instance_id=unit_id,
                    )
                )
            )
            if not was_eligible:
                continue
            if not legal_consolidation_modes(
                scenario=scenario,
                ruleset_descriptor=state.runtime_ruleset_descriptor(),
                unit_instance_id=unit_id,
                objective_markers=_objective_markers_for_state(state),
            ):
                continue
            eligible.append(unit_id)
            continue
        raise GameLifecycleError("Unsupported fight movement eligibility step.")
    del policy
    return tuple(sorted(eligible))


def _eligible_fight_movement_unit_ids_for_request(
    *,
    state: GameState,
    proposal_request: MovementProposalRequest,
    ruleset_descriptor: RulesetDescriptor,
) -> tuple[str, ...]:
    fight_state = _require_fight_state(state)
    if _is_overrun_movement_request(proposal_request):
        activation = fight_state.active_activation
        if activation is None:
            return ()
        return (activation.unit_instance_id,)
    return _eligible_fight_movement_unit_ids(
        state=state,
        fight_state=fight_state,
        policy=ruleset_descriptor.fight_policy,
        step=_fight_step_for_proposal_kind(proposal_request.proposal_kind),
        player_id=proposal_request.actor_id,
    )


def _parse_fight_movement_proposal_or_invalid(
    *,
    state: GameState,
    proposal_request: MovementProposalRequest,
    result: DecisionResult,
) -> FightMovementProposal | LifecycleStatus:
    try:
        return fight_movement_proposal_from_payload(result.payload)
    except (GameLifecycleError, GeometryError, KeyError, TypeError) as exc:
        return _reject_invalid_fight_proposal(
            state=state,
            proposal_validation=fight_movement_proposal_payload_parse_failure(
                proposal_request=proposal_request,
                error=exc,
            ),
            message="Fight movement proposal payload is malformed.",
        )


def _parse_melee_declaration_or_invalid(
    *,
    state: GameState,
    proposal_request: MeleeDeclarationProposalRequest,
    result: DecisionResult,
) -> MeleeDeclarationProposal | LifecycleStatus:
    try:
        return melee_declaration_proposal_from_payload(result.payload)
    except (GameLifecycleError, KeyError, TypeError) as exc:
        return _reject_invalid_fight_proposal(
            state=state,
            proposal_validation=ProposalValidationResult.invalid(
                proposal_request_id=proposal_request.request_id,
                proposal_kind=ProposalKind.MELEE_DECLARATION,
                violation_code="proposal_payload_malformed",
                message=f"Melee declaration proposal payload is malformed: {exc}",
                field="payload",
            ),
            message="Melee declaration proposal payload is malformed.",
        )


def _reject_invalid_fight_proposal(
    *,
    state: GameState,
    proposal_validation: ProposalValidationResult,
    message: str,
) -> LifecycleStatus:
    return LifecycleStatus.invalid(
        stage=state.stage,
        message=message,
        payload={
            "phase": BattlePhase.FIGHT.value,
            "phase_body_status": _FIGHT_MOVEMENT_INVALID_STATUS,
            "proposal_validation": validate_json_value(proposal_validation.to_payload()),
        },
    )


def _reject_recorded_invalid_fight_movement(
    *,
    state: GameState,
    decisions: DecisionController,
    result: DecisionResult,
    proposal_request: MovementProposalRequest,
    proposal_validation: ProposalValidationResult,
    resolution: FightMovementResolution | None,
    message: str,
) -> LifecycleStatus:
    violation_code = _first_proposal_violation_code(proposal_validation)
    event_payload: dict[str, JsonValue] = {
        "game_id": state.game_id,
        "battle_round": state.battle_round,
        "active_player_id": _active_player_id(state),
        "phase": BattlePhase.FIGHT.value,
        "unit_instance_id": proposal_request.unit_instance_id,
        "request_id": result.request_id,
        "result_id": result.result_id,
        "phase_body_status": _FIGHT_MOVEMENT_INVALID_STATUS,
        "violation_code": violation_code,
        "proposal_request_id": proposal_request.request_id,
        "proposal_kind": proposal_request.proposal_kind.value,
        "movement_phase_action": proposal_request.movement_phase_action,
        "proposal_validation": validate_json_value(proposal_validation.to_payload()),
    }
    if resolution is not None:
        event_payload["resolution"] = validate_json_value(resolution.to_payload())
    invalid_payload = validate_json_value(event_payload)
    decisions.event_log.append("fight_movement_invalid", invalid_payload)
    retry_request = _request_fight_movement_proposal_retry(
        state=state,
        decisions=decisions,
        proposal_request=proposal_request,
        rejected_result=result,
    )
    return LifecycleStatus.invalid(
        stage=GameLifecycleStage.BATTLE,
        message=message,
        payload={
            "phase": BattlePhase.FIGHT.value,
            "phase_body_status": _FIGHT_MOVEMENT_INVALID_STATUS,
            "battle_round": state.battle_round,
            "active_player_id": _active_player_id(state),
            "unit_instance_id": proposal_request.unit_instance_id,
            "movement_phase_action": proposal_request.movement_phase_action,
            "proposal_kind": proposal_request.proposal_kind.value,
            "violation_code": violation_code,
            "next_request_id": retry_request.request_id,
            "proposal_validation": validate_json_value(proposal_validation.to_payload()),
        },
    )


def _fight_movement_witness_matches_current_unit_status(
    *,
    state: GameState,
    proposal_request: MovementProposalRequest,
    proposal: FightMovementProposal,
) -> ProposalValidationResult | None:
    witness = proposal.witness
    if witness is None:
        return None
    unit_placement = _battlefield_scenario(state).battlefield_state.unit_placement_by_id(
        proposal.unit_instance_id
    )
    expected_model_ids = tuple(
        sorted(placement.model_instance_id for placement in unit_placement.model_placements)
    )
    if tuple(sorted(witness.model_ids())) != expected_model_ids:
        return ProposalValidationResult.invalid(
            proposal_request_id=proposal_request.request_id,
            proposal_kind=proposal_request.proposal_kind,
            violation_code="fight_movement_witness_model_drift",
            message="Fight movement witness must match selected unit models.",
            field="witness",
            status="stale",
        )
    for placement in unit_placement.model_placements:
        if witness.poses_for_model(placement.model_instance_id)[0] != placement.pose:
            return ProposalValidationResult.invalid(
                proposal_request_id=proposal_request.request_id,
                proposal_kind=proposal_request.proposal_kind,
                violation_code="fight_movement_witness_start_drift",
                message="Fight movement witness must start at current model poses.",
                field="witness",
                status="stale",
            )
    return None


def _proposal_validation_has_code(
    proposal_validation: ProposalValidationResult,
    violation_code: str,
) -> bool:
    return any(
        violation.violation_code == violation_code for violation in proposal_validation.violations
    )


def _first_proposal_violation_code(proposal_validation: ProposalValidationResult) -> str:
    if not proposal_validation.violations:
        raise GameLifecycleError("Invalid proposal validation requires at least one violation.")
    return proposal_validation.violations[0].violation_code


def _fight_movement_invalid_message(violation_code: str) -> str:
    if violation_code == _ENDPOINT_ONLY_PATH_VIOLATION_CODE:
        return "Fight movement PathWitness must not repeat only endpoint poses."
    if violation_code == "movement_distance_exceeded":
        return "Fight movement path exceeds the maximum distance."
    if violation_code in {
        "path_intersects_model",
        "path_intersects_battlefield_feature",
        "path_exits_battlefield",
        "terrain_blocked",
        "movement_endpoint_coherency_failed",
    }:
        return "Fight movement path is not legal."
    return "Fight movement proposal endpoint is not legal."


def _fight_attack_sequence_for_request(
    *,
    state: GameState,
    request: DecisionRequest,
) -> AttackSequence:
    payload = _decision_payload_object(request.payload)
    sequence_id = _payload_string(payload, key="sequence_id")
    fight_state = state.fight_phase_state
    if (
        fight_state is not None
        and fight_state.attack_sequence is not None
        and fight_state.attack_sequence.sequence_id == sequence_id
    ):
        return fight_state.attack_sequence
    raise GameLifecycleError("Fight attack sequence request has no active sequence.")


def _invalid_if_current_option_payload_drifted(
    *,
    state: GameState,
    result: DecisionResult,
    expected_request: DecisionRequest,
    invalid_reason: str,
) -> LifecycleStatus | None:
    try:
        expected_option = expected_request.option_by_id(result.selected_option_id)
    except DecisionError:
        return LifecycleStatus.invalid(
            stage=state.stage,
            message="Fight attack sequence option is no longer legal.",
            payload={
                "invalid_reason": invalid_reason,
                "selected_option_id": result.selected_option_id,
            },
        )
    if result.payload != expected_option.payload:
        return LifecycleStatus.invalid(
            stage=state.stage,
            message="Fight attack sequence payload drifted.",
            payload={
                "invalid_reason": invalid_reason,
                "selected_option_id": result.selected_option_id,
            },
        )
    return None


def _is_overrun_movement_request(proposal_request: MovementProposalRequest) -> bool:
    context = proposal_request.context or {}
    return context.get("fight_movement_timing") == "overrun"


def _fight_activation_effect_id_suffix(effect_kind: str) -> str:
    if effect_kind == FIGHT_ACTIVATION_MELEE_TARGETING_EFFECT_KIND:
        return "melee-targeting"
    if effect_kind in FIGHT_ACTIVATION_ABILITY_EFFECT_KINDS:
        return effect_kind.replace("_", "-")
    raise GameLifecycleError("Unsupported fight activation effect kind.")


def _battlefield_scenario(state: GameState) -> BattlefieldScenario:
    battlefield_state = state.battlefield_state
    if battlefield_state is None:
        raise GameLifecycleError("Fight phase requires battlefield_state.")
    try:
        return BattlefieldScenario(
            armies=tuple(state.army_definitions),
            battlefield_state=battlefield_state,
        )
    except PlacementError as exc:
        raise GameLifecycleError("Fight battlefield scenario is invalid.") from exc


def _objective_markers_for_state(state: GameState) -> tuple[ObjectiveMarker, ...]:
    if state.mission_setup is None:
        return ()
    return tuple(marker.to_objective_marker() for marker in state.mission_setup.objective_markers)


def _unit_ids_for_player(*, state: GameState, player_id: str) -> tuple[str, ...]:
    requested_player_id = _validate_identifier("player_id", player_id)
    army = state.army_definition_for_player(requested_player_id)
    if army is None:
        raise GameLifecycleError("Fight phase requires mustered army definitions.")
    placed_unit_ids = _placed_unit_ids(state)
    return tuple(
        unit.unit_instance_id for unit in army.units if unit.unit_instance_id in placed_unit_ids
    )


def _unit_by_id(*, state: GameState, unit_instance_id: str) -> UnitInstance:
    requested_unit_id = _validate_identifier("unit_instance_id", unit_instance_id)
    for army in state.army_definitions:
        for unit in army.units:
            if unit.unit_instance_id == requested_unit_id:
                return unit
    raise GameLifecycleError("Fight unit was not found.")


def _placed_unit_ids(state: GameState) -> set[str]:
    battlefield_state = state.battlefield_state
    if battlefield_state is None:
        raise GameLifecycleError("Fight phase requires battlefield_state.")
    return {
        unit_placement.unit_instance_id
        for placed_army in battlefield_state.placed_armies
        for unit_placement in placed_army.unit_placements
    }


def _payload_string(payload: dict[str, JsonValue], *, key: str) -> str:
    value = payload.get(key)
    if type(value) is not str:
        raise GameLifecycleError(f"{key} must be a string.")
    return value


def _payload_int(payload: dict[str, JsonValue], *, key: str) -> int:
    value = payload.get(key)
    if type(value) is not int:
        raise GameLifecycleError(f"{key} must be an integer.")
    return value


@dataclass(frozen=True, slots=True)
class _FightRequestContext:
    fight_state: FightPhaseState
    contexts: tuple[FightEligibilityContext, ...]
    pass_available: bool


def invalid_fight_phase_start_faction_rule_status(
    *,
    state: GameState,
    request: DecisionRequest,
    result: DecisionResult,
) -> LifecycleStatus | None:
    invalid_status = _invalid_finite_decision_status(
        state=state,
        request=request,
        result=result,
        invalid_reason="invalid_fight_phase_start_faction_rule_result",
    )
    if invalid_status is not None:
        return invalid_status
    payload = _decision_payload_object(result.payload)
    request_payload = _decision_payload_object(request.payload)
    drift_reason = _fight_phase_start_faction_rule_drift_reason(
        state=state,
        request=request,
        result=result,
        payload=payload,
        request_payload=request_payload,
    )
    if drift_reason is None:
        return None
    return LifecycleStatus.invalid(
        stage=state.stage,
        message="Fight phase start faction rule option drifted.",
        payload=validate_json_value(
            {
                "game_id": state.game_id,
                "player_id": result.actor_id,
                "battle_round": state.battle_round,
                "phase": (
                    None if state.current_battle_phase is None else state.current_battle_phase.value
                ),
                "invalid_reason": drift_reason,
            }
        ),
    )


def _fight_phase_start_faction_rule_drift_reason(
    *,
    state: GameState,
    request: DecisionRequest,
    result: DecisionResult,
    payload: dict[str, JsonValue],
    request_payload: dict[str, JsonValue],
) -> str | None:
    if result.actor_id is None:
        return "actor_missing"
    if request.actor_id != result.actor_id:
        return "actor_player_drift"
    if _payload_string(payload, key="game_id") != state.game_id:
        return "game_id_drift"
    if _payload_int(payload, key="battle_round") != state.battle_round:
        return "battle_round_drift"
    if _payload_string(payload, key="phase") != BattlePhase.FIGHT.value:
        return "payload_phase_drift"
    if _payload_string(payload, key="active_player_id") != _active_player_id(state):
        return "active_player_drift"
    if _payload_string(request_payload, key="game_id") != state.game_id:
        return "request_game_id_drift"
    if _payload_int(request_payload, key="battle_round") != state.battle_round:
        return "request_battle_round_drift"
    if _payload_string(request_payload, key="phase") != BattlePhase.FIGHT.value:
        return "request_phase_drift"
    if _payload_string(request_payload, key="active_player_id") != _active_player_id(state):
        return "request_active_player_drift"
    if state.current_battle_phase is not BattlePhase.FIGHT:
        return "phase_drift"
    if state.fight_phase_state is not None:
        return "fight_phase_start_window_closed"
    return None


def invalid_fight_activation_status(
    *,
    state: GameState,
    request: DecisionRequest,
    result: DecisionResult,
    ruleset_descriptor: RulesetDescriptor,
) -> LifecycleStatus | None:
    invalid_status = _invalid_finite_decision_status(
        state=state,
        request=request,
        result=result,
        invalid_reason="invalid_fight_activation_result",
    )
    if invalid_status is not None:
        return invalid_status
    fight_state = state.fight_phase_state
    if fight_state is None:
        return LifecycleStatus.invalid(
            stage=state.stage,
            message="Fight activation selection has no active fight phase state.",
            payload={
                "invalid_reason": "invalid_fight_activation_result",
                "field": "fight_phase_state",
            },
        )
    policy = ruleset_descriptor.fight_policy
    current_contexts = eligible_fight_contexts_for_player(
        state=state,
        fight_state=fight_state,
        player_id=_require_actor(result),
        policy=policy,
    )
    if result.selected_option_id == ELIGIBLE_TO_FIGHT_PASS_OPTION_ID:
        return _invalid_fight_pass_status(
            state=state,
            result=result,
            fight_state=fight_state,
            current_contexts=current_contexts,
            policy=policy,
        )
    return _invalid_fight_activation_selection_status(
        state=state,
        result=result,
        fight_state=fight_state,
        current_contexts=current_contexts,
        policy=policy,
    )


def invalid_fight_activation_ability_status(
    *,
    state: GameState,
    request: DecisionRequest,
    result: DecisionResult,
    decisions: DecisionController,
) -> LifecycleStatus | None:
    invalid_status = _invalid_finite_decision_status(
        state=state,
        request=request,
        result=result,
        invalid_reason="invalid_fight_activation_ability_result",
    )
    if invalid_status is not None:
        return invalid_status
    fight_state = state.fight_phase_state
    if fight_state is None:
        return LifecycleStatus.invalid(
            stage=state.stage,
            message="Fight activation ability has no active fight phase state.",
            payload={
                "invalid_reason": "invalid_fight_activation_ability_result",
                "field": "fight_phase_state",
            },
        )
    activation = fight_state.active_activation
    if activation is None:
        return LifecycleStatus.invalid(
            stage=state.stage,
            message="Fight activation ability has no active activation.",
            payload={
                "invalid_reason": "invalid_fight_activation_ability_result",
                "field": "active_activation",
            },
        )
    if ability_request_activation_payload(request) != activation.to_payload():
        return LifecycleStatus.invalid(
            stage=state.stage,
            message="Fight activation ability activation context is stale.",
            payload={
                "invalid_reason": "invalid_fight_activation_ability_result",
                "field": "activation_selection",
            },
        )
    if _fight_activation_ability_window_resolved(
        state=state,
        decisions=decisions,
        activation=activation,
    ):
        return LifecycleStatus.invalid(
            stage=state.stage,
            message="Fight activation ability window has already resolved.",
            payload={
                "invalid_reason": "invalid_fight_activation_ability_result",
                "field": "activation_result_id",
            },
        )
    if result.selected_option_id == DECLINE_FIGHT_ACTIVATION_ABILITY_OPTION_ID:
        return None
    ability_use = fight_activation_ability_use_from_result(
        payload=result.payload,
        request_id=result.request_id,
        result_id=result.result_id,
    )
    if ability_use.activation_result_id != activation.result_id:
        return LifecycleStatus.invalid(
            stage=state.stage,
            message="Fight activation ability result activation drifted.",
            payload={
                "invalid_reason": "invalid_fight_activation_ability_result",
                "field": "activation_result_id",
            },
        )
    if ability_use.activation_request_id != activation.request_id:
        return LifecycleStatus.invalid(
            stage=state.stage,
            message="Fight activation ability result activation request drifted.",
            payload={
                "invalid_reason": "invalid_fight_activation_ability_result",
                "field": "activation_request_id",
            },
        )
    if ability_use.unit_instance_id != activation.unit_instance_id:
        return LifecycleStatus.invalid(
            stage=state.stage,
            message="Fight activation ability result unit drifted.",
            payload={
                "invalid_reason": "invalid_fight_activation_ability_result",
                "field": "unit_instance_id",
            },
        )
    return None


def invalid_fight_interrupt_status(
    *,
    state: GameState,
    request: DecisionRequest,
    result: DecisionResult,
    ruleset_descriptor: RulesetDescriptor,
) -> LifecycleStatus | None:
    invalid_status = _invalid_finite_decision_status(
        state=state,
        request=request,
        result=result,
        invalid_reason="invalid_fight_interrupt_result",
    )
    if invalid_status is not None:
        return invalid_status
    fight_state = state.fight_phase_state
    if fight_state is None:
        return LifecycleStatus.invalid(
            stage=state.stage,
            message="Fight interrupt has no active fight phase state.",
            payload={
                "invalid_reason": "invalid_fight_interrupt_result",
                "field": "fight_phase_state",
            },
        )
    interrupt = fight_interrupt_request_from_payload(result.payload)
    fight_order_state = fight_state.fight_order_state
    if interrupt.interrupt_id in fight_order_state.resolved_interrupt_ids:
        return LifecycleStatus.invalid(
            stage=state.stage,
            message="Fight interrupt has already resolved.",
            payload={
                "invalid_reason": "invalid_fight_interrupt_result",
                "field": "interrupt_id",
            },
        )
    if interrupt.source_effect_id in fight_order_state.resolved_interrupt_source_effect_ids:
        return LifecycleStatus.invalid(
            stage=state.stage,
            message="Fight interrupt source has already resolved.",
            payload={
                "invalid_reason": "invalid_fight_interrupt_result",
                "field": "source_effect_id",
            },
        )
    if result.selected_option_id == DECLINE_FIGHT_INTERRUPT_OPTION_ID:
        return None
    policy = ruleset_descriptor.fight_policy
    current_contexts = eligible_fight_contexts_for_player(
        state=state,
        fight_state=fight_state,
        player_id=interrupt.player_id,
        policy=policy,
    )
    selected = current_fight_activation_selection_from_payload(
        result_payload=result.payload,
        request_id=result.request_id,
        result_id=result.result_id,
        interrupt_id=interrupt.interrupt_id,
    )
    matching_context = _matching_context(current_contexts, selected.unit_instance_id)
    if matching_context is None:
        return LifecycleStatus.invalid(
            stage=state.stage,
            message="Fight interrupt selected unit is no longer eligible.",
            payload={
                "invalid_reason": "invalid_fight_interrupt_result",
                "field": "unit_instance_id",
            },
        )
    if selected.unit_instance_id not in interrupt.eligible_unit_ids:
        return LifecycleStatus.invalid(
            stage=state.stage,
            message="Fight interrupt selected a unit outside the interrupt snapshot.",
            payload={
                "invalid_reason": "invalid_fight_interrupt_result",
                "field": "eligible_unit_ids",
            },
        )
    expected_option_id = fight_activation_option_id(
        unit_instance_id=selected.unit_instance_id,
        fight_type=selected.fight_type,
    )
    if result.selected_option_id != expected_option_id:
        return LifecycleStatus.invalid(
            stage=state.stage,
            message="Fight interrupt selected option does not match its payload.",
            payload={
                "invalid_reason": "invalid_fight_interrupt_result",
                "field": "selected_option_id",
            },
        )
    if selected.fight_type not in legal_fight_types_for_context(
        context=matching_context,
        policy=policy,
    ):
        return LifecycleStatus.invalid(
            stage=state.stage,
            message="Fight interrupt selected fight type is not legal for that unit.",
            payload={
                "invalid_reason": "invalid_fight_interrupt_result",
                "field": "fight_type",
            },
        )
    if matching_context.to_payload() != _context_payload_from_result(result):
        return LifecycleStatus.invalid(
            stage=state.stage,
            message="Fight interrupt eligibility context is stale.",
            payload={
                "invalid_reason": "invalid_fight_interrupt_result",
                "field": "eligibility_context",
            },
        )
    return None


def _ensure_fight_phase_state(
    *,
    state: GameState,
    decisions: DecisionController,
    policy: FightPolicyDescriptor,
) -> FightPhaseState:
    fight_state = state.fight_phase_state
    if fight_state is not None:
        return fight_state
    active_player_id = _active_player_id(state)
    registry = FightsFirstRegistry.from_state(state)
    started = FightPhaseState.start(
        battle_round=state.battle_round,
        active_player_id=active_player_id,
        policy=policy,
        engaged_at_fight_step_start_unit_ids=engaged_unit_ids_at_fight_start(
            state=state,
            policy=policy,
        ),
        fights_first_registry=registry,
    )
    state.replace_fight_phase_state(started)
    decisions.event_log.append(
        "fight_phase_started",
        _fight_phase_status_payload(
            state=state,
            fight_state=started,
            phase_body_status="fight_phase_started",
        ),
    )
    return started


def _request_fight_phase_start_rule_if_available(
    *,
    handler: FightPhaseHandler,
    state: GameState,
    decisions: DecisionController,
) -> LifecycleStatus | None:
    request = handler.fight_phase_start_hooks.next_request_for(
        FightPhaseStartRequestContext(
            state=state,
            decisions=decisions,
        )
    )
    if request is None:
        return None
    decisions.request_decision(request)
    decisions.event_log.append(
        "fight_phase_start_faction_rule_requested",
        validate_json_value(
            {
                "game_id": state.game_id,
                "battle_round": state.battle_round,
                "active_player_id": _active_player_id(state),
                "phase": BattlePhase.FIGHT.value,
                "decision_type": request.decision_type,
                "request_id": request.request_id,
                "actor_id": request.actor_id,
            }
        ),
    )
    return LifecycleStatus.waiting_for_decision(
        stage=GameLifecycleStage.BATTLE,
        decision_request=request,
        payload=validate_json_value(
            {
                "phase": BattlePhase.FIGHT.value,
                "active_player_id": _active_player_id(state),
                "phase_body_status": "fight_phase_start_faction_rule_pending",
                "request_id": request.request_id,
            }
        ),
    )


def _advance_to_next_fight_request(
    *,
    state: GameState,
    fight_state: FightPhaseState,
    policy: FightPolicyDescriptor,
) -> _FightRequestContext:
    current = fight_state
    checked_player_ids: set[str] = set()
    for _iteration in range(
        len(state.player_ids) * (len(current.fight_order_state.ordering_bands) + 1) * 2
    ):
        if current.phase_complete:
            return _FightRequestContext(
                fight_state=current,
                contexts=(),
                pass_available=False,
            )
        if (
            current.current_ordering_band is FightOrderingBandKind.REMAINING_COMBATS
            and current.fight_order_state.remaining_combats_activation_since_band_entry
            and _fights_first_contexts_available(
                state=state,
                fight_state=current,
                policy=policy,
            )
        ):
            current = current.with_ordering_band(
                ordering_band=FightOrderingBandKind.FIGHTS_FIRST,
                next_player_id=current.active_player_id,
            )
            checked_player_ids = set()
            continue
        contexts = (
            ()
            if current.fight_order_state.next_player_id
            in current.fight_order_state.passed_player_ids
            else eligible_fight_contexts_for_player(
                state=state,
                fight_state=current,
                player_id=current.fight_order_state.next_player_id,
                policy=policy,
            )
        )
        if contexts:
            return _FightRequestContext(
                fight_state=current,
                contexts=contexts,
                pass_available=eligible_pass_is_available(contexts),
            )
        checked_player_ids.add(current.fight_order_state.next_player_id)
        if len(checked_player_ids) < len(state.player_ids):
            current = current.with_next_player(
                _next_player_id(
                    player_ids=state.player_ids,
                    current_player_id=current.fight_order_state.next_player_id,
                )
            )
            continue
        current = current.with_next_band()
        checked_player_ids = set()
    raise GameLifecycleError("Fight phase exceeded deterministic ordering guard.")


def _request_active_fight_phase_stratagem_if_available(
    *,
    handler: FightPhaseHandler,
    state: GameState,
    decisions: DecisionController,
    fight_state: FightPhaseState,
    contexts: tuple[FightEligibilityContext, ...],
) -> LifecycleStatus | None:
    from warhammer40k_core.engine.stratagems import (
        create_stratagem_use_decision_request,
        stratagem_decline_option,
        stratagem_use_options_from_index,
    )

    if type(fight_state) is not FightPhaseState:
        raise GameLifecycleError("Active fight stratagem trigger requires fight state.")
    context = StratagemEligibilityContext.from_state(
        state=state,
        player_id=fight_state.fight_order_state.next_player_id,
        trigger_kind=TimingTriggerKind.DURING_PHASE,
        timing_window_id=_active_fight_phase_stratagem_timing_window_id(fight_state),
        trigger_payload={
            "ordering_band": fight_state.current_ordering_band.value,
            "next_player_id": fight_state.fight_order_state.next_player_id,
            "eligible_unit_instance_ids": [context.unit_instance_id for context in contexts],
            "selected_to_fight_unit_instance_ids": list(
                fight_state.fight_order_state.selected_to_fight_unit_ids
            ),
        },
    )
    if stratagem_window_declined_for_context(decisions=decisions, context=context):
        return None
    if _stratagem_used_for_context(decisions=decisions, context=context):
        return None
    options = stratagem_use_options_from_index(
        state=state,
        index=handler.stratagem_index,
        context=context,
    )
    if not options:
        return None
    request = create_stratagem_use_decision_request(
        state=state,
        context=context,
        options=(*options, stratagem_decline_option()),
    )
    decisions.request_decision(request)
    decisions.event_log.append(
        "active_fight_phase_stratagem_window_opened",
        validate_json_value(
            {
                "game_id": state.game_id,
                "battle_round": state.battle_round,
                "active_player_id": fight_state.active_player_id,
                "phase": BattlePhase.FIGHT.value,
                "player_id": fight_state.fight_order_state.next_player_id,
                "stratagem_context": context.to_payload(),
                "request_id": request.request_id,
                "phase_body_status": "active_fight_phase_stratagem_pending",
            }
        ),
    )
    return LifecycleStatus.waiting_for_decision(
        stage=GameLifecycleStage.BATTLE,
        decision_request=request,
        payload={
            "phase": BattlePhase.FIGHT.value,
            "battle_round": state.battle_round,
            "active_player_id": fight_state.active_player_id,
            "player_id": fight_state.fight_order_state.next_player_id,
            "phase_body_status": "active_fight_phase_stratagem_pending",
            "pending_request_id": request.request_id,
        },
    )


def _active_fight_phase_stratagem_timing_window_id(fight_state: FightPhaseState) -> str:
    if type(fight_state) is not FightPhaseState:
        raise GameLifecycleError("Active fight stratagem timing requires fight state.")
    return (
        f"active-fight-stratagem:round-{fight_state.battle_round}:"
        f"player-{fight_state.fight_order_state.next_player_id}:"
        f"band-{fight_state.current_ordering_band.value}:"
        f"selected-{len(fight_state.fight_order_state.selected_to_fight_unit_ids)}"
    )


def _stratagem_used_for_context(
    *,
    decisions: DecisionController,
    context: StratagemEligibilityContext,
) -> bool:
    context_payload = context.to_payload()
    for record in decisions.event_log.records:
        if record.event_type != "stratagem_used":
            continue
        payload = record.payload
        if not isinstance(payload, dict):
            raise GameLifecycleError("Stratagem use event payload must be an object.")
        payload_object = cast(dict[str, object], payload)
        if (
            payload_object.get("game_id") == context_payload.get("game_id")
            and payload_object.get("player_id") == context_payload.get("player_id")
            and payload_object.get("battle_round") == context_payload.get("battle_round")
            and payload_object.get("phase") == context_payload.get("phase")
            and payload_object.get("active_player_id") == context_payload.get("active_player_id")
            and payload_object.get("timing_window_id") == context_payload.get("timing_window_id")
        ):
            return True
    return False


def _request_fight_activation(
    *,
    state: GameState,
    decisions: DecisionController,
    fight_state: FightPhaseState,
    contexts: tuple[FightEligibilityContext, ...],
    pass_available: bool,
    policy: FightPolicyDescriptor,
) -> LifecycleStatus:
    request = DecisionRequest(
        request_id=state.next_decision_request_id(),
        decision_type=FIGHT_ACTIVATION_DECISION_TYPE,
        actor_id=fight_state.fight_order_state.next_player_id,
        payload=validate_json_value(
            {
                "game_id": state.game_id,
                "battle_round": state.battle_round,
                "phase": BattlePhase.FIGHT.value,
                "active_player_id": fight_state.active_player_id,
                "player_id": fight_state.fight_order_state.next_player_id,
                "step_states": [step.to_payload() for step in fight_state.step_states],
                "ordering_band": fight_state.current_ordering_band.value,
                "eligible_contexts": [context.to_payload() for context in contexts],
                "eligible_pass_available": pass_available,
            }
        ),
        options=_fight_activation_options(
            state=state,
            fight_state=fight_state,
            contexts=contexts,
            pass_available=pass_available,
            policy=policy,
        ),
    )
    decisions.request_decision(request)
    decisions.event_log.append(
        "fight_activation_selection_requested",
        validate_json_value(
            {
                "game_id": state.game_id,
                "battle_round": state.battle_round,
                "phase": BattlePhase.FIGHT.value,
                "active_player_id": fight_state.active_player_id,
                "player_id": fight_state.fight_order_state.next_player_id,
                "ordering_band": fight_state.current_ordering_band.value,
                "request_id": request.request_id,
                "eligible_unit_ids": [context.unit_instance_id for context in contexts],
                "eligible_pass_available": pass_available,
                "phase_body_status": _FIGHT_ACTIVATION_REQUIRED_STATUS,
            }
        ),
    )
    return LifecycleStatus.waiting_for_decision(
        stage=GameLifecycleStage.BATTLE,
        decision_request=request,
        payload={
            "phase": BattlePhase.FIGHT.value,
            "phase_body_status": _FIGHT_ACTIVATION_REQUIRED_STATUS,
            "battle_round": state.battle_round,
            "active_player_id": fight_state.active_player_id,
            "player_id": fight_state.fight_order_state.next_player_id,
            "ordering_band": fight_state.current_ordering_band.value,
            "eligible_unit_ids": [context.unit_instance_id for context in contexts],
            "eligible_pass_available": pass_available,
        },
    )


def _fight_activation_options(
    *,
    state: GameState,
    fight_state: FightPhaseState,
    contexts: tuple[FightEligibilityContext, ...],
    pass_available: bool,
    policy: FightPolicyDescriptor,
) -> tuple[DecisionOption, ...]:
    options: list[DecisionOption] = []
    for context in contexts:
        for fight_type in legal_fight_types_for_context(context=context, policy=policy):
            options.append(
                DecisionOption(
                    option_id=fight_activation_option_id(
                        unit_instance_id=context.unit_instance_id,
                        fight_type=fight_type,
                    ),
                    label=f"{context.unit_instance_id} {fight_type.value}",
                    payload=fight_activation_option_payload(
                        state=state,
                        fight_state=fight_state,
                        context=context,
                        fight_type=fight_type,
                    ),
                )
            )
    if pass_available:
        options.append(
            DecisionOption(
                option_id=ELIGIBLE_TO_FIGHT_PASS_OPTION_ID,
                label="Eligible To Fight Pass",
                payload=eligible_pass_option_payload(
                    state=state,
                    fight_state=fight_state,
                    player_id=fight_state.fight_order_state.next_player_id,
                    contexts=contexts,
                    policy=policy,
                ),
            )
        )
    return tuple(options)


def _fights_first_contexts_available(
    *,
    state: GameState,
    fight_state: FightPhaseState,
    policy: FightPolicyDescriptor,
) -> bool:
    fights_first_state = fight_state.with_ordering_band(
        ordering_band=FightOrderingBandKind.FIGHTS_FIRST,
        next_player_id=fight_state.active_player_id,
    )
    return any(
        eligible_fight_contexts_for_player(
            state=state,
            fight_state=fights_first_state,
            player_id=player_id,
            policy=policy,
        )
        for player_id in state.player_ids
    )


def _apply_fight_activation_decision(
    *,
    handler: FightPhaseHandler,
    state: GameState,
    result: DecisionResult,
    decisions: DecisionController,
    reaction_queue: ReactionQueue | None,
    policy: FightPolicyDescriptor,
) -> LifecycleStatus | None:
    fight_state = _require_fight_state(state)
    if result.selected_option_id == ELIGIBLE_TO_FIGHT_PASS_OPTION_ID:
        eligible_pass = current_eligible_pass_from_payload(
            result_payload=result.payload,
            request_id=result.request_id,
            result_id=result.result_id,
        )
        state.replace_fight_phase_state(
            fight_state.with_eligible_pass(eligible_pass).with_next_player(
                _next_player_id(
                    player_ids=state.player_ids,
                    current_player_id=eligible_pass.player_id,
                )
            )
        )
        decisions.event_log.append(
            "eligible_to_fight_pass_recorded",
            validate_json_value(
                {
                    "game_id": state.game_id,
                    "battle_round": state.battle_round,
                    "phase": BattlePhase.FIGHT.value,
                    "phase_body_status": _FIGHT_PASS_RECORDED_STATUS,
                    "eligible_pass": eligible_pass.to_payload(),
                }
            ),
        )
        return None

    selection = current_fight_activation_selection_from_payload(
        result_payload=result.payload,
        request_id=result.request_id,
        result_id=result.result_id,
    )
    activated_state = (
        fight_state.with_activation(selection)
        .with_next_player(
            _next_player_id(player_ids=state.player_ids, current_player_id=selection.player_id)
        )
        .with_active_activation(selection)
    )
    state.replace_fight_phase_state(activated_state)
    decisions.event_log.append(
        "fight_activation_selected",
        validate_json_value(
            {
                "game_id": state.game_id,
                "battle_round": state.battle_round,
                "phase": BattlePhase.FIGHT.value,
                "phase_body_status": _FIGHT_ACTIVATION_RECORDED_STATUS,
                "activation_selection": selection.to_payload(),
            }
        ),
    )
    _apply_fight_unit_selected_effect_grants(
        state=state,
        decisions=decisions,
        activation=selection,
        registry=handler.fight_unit_selected_hooks,
    )
    del reaction_queue, policy
    return _request_fight_unit_selected_grant_decision_if_available(
        state=state,
        decisions=decisions,
        activation=selection,
        registry=handler.fight_unit_selected_grant_hooks,
    )


def _apply_fight_unit_selected_effect_grants(
    *,
    state: GameState,
    decisions: DecisionController,
    activation: FightActivationSelection,
    registry: FightUnitSelectedHookRegistry,
) -> None:
    if type(registry) is not FightUnitSelectedHookRegistry:
        raise GameLifecycleError("Fight-unit-selected effect grants require a registry.")
    context = _fight_unit_selected_context(state=state, activation=activation)
    for grant in registry.grants_for(context):
        state.record_persisting_effect(grant.persisting_effect)
        decisions.event_log.append(
            grant.event_type,
            validate_json_value(
                {
                    "game_id": state.game_id,
                    "battle_round": state.battle_round,
                    "phase": BattlePhase.FIGHT.value,
                    "active_player_id": state.active_player_id,
                    "player_id": activation.player_id,
                    "unit_instance_id": activation.unit_instance_id,
                    "request_id": activation.request_id,
                    "result_id": activation.result_id,
                    "grant": grant.to_payload(),
                    "persisting_effect": grant.persisting_effect.to_payload(),
                }
            ),
        )


def _request_fight_unit_selected_grant_decision_if_available(
    *,
    state: GameState,
    decisions: DecisionController,
    activation: FightActivationSelection,
    registry: FightUnitSelectedGrantRegistry,
) -> LifecycleStatus | None:
    context = _fight_unit_selected_context(state=state, activation=activation)
    grants = registry.grants_for(context)
    if not grants:
        return None
    request = DecisionRequest(
        request_id=state.next_decision_request_id(),
        decision_type=SELECT_FIGHT_UNIT_GRANT_DECISION_TYPE,
        actor_id=activation.player_id,
        payload=validate_json_value(
            {
                "game_id": state.game_id,
                "battle_round": state.battle_round,
                "phase": BattlePhase.FIGHT.value,
                "active_player_id": state.active_player_id,
                "player_id": activation.player_id,
                "unit_instance_id": activation.unit_instance_id,
                "activation_request_id": activation.request_id,
                "activation_result_id": activation.result_id,
            }
        ),
        options=_fight_unit_selected_grant_options(activation=activation, grants=grants),
    )
    decisions.request_decision(request)
    decisions.event_log.append(
        "fight_unit_selected_grant_decision_requested",
        validate_json_value(
            {
                "game_id": state.game_id,
                "battle_round": state.battle_round,
                "phase": BattlePhase.FIGHT.value,
                "active_player_id": state.active_player_id,
                "player_id": activation.player_id,
                "unit_instance_id": activation.unit_instance_id,
                "activation_selection": activation.to_payload(),
                "available_fight_unit_grants": [grant.to_payload() for grant in grants],
                "phase_body_status": "fight_unit_selected_grant_decision_pending",
            }
        ),
    )
    return LifecycleStatus.waiting_for_decision(
        stage=GameLifecycleStage.BATTLE,
        decision_request=request,
        payload={
            "phase": BattlePhase.FIGHT.value,
            "phase_body_status": "fight_unit_selected_grant_decision_pending",
            "battle_round": state.battle_round,
            "active_player_id": state.active_player_id,
            "player_id": activation.player_id,
            "unit_instance_id": activation.unit_instance_id,
        },
    )


def _fight_unit_selected_grant_options(
    *,
    activation: FightActivationSelection,
    grants: tuple[FightUnitSelectedGrant, ...],
) -> tuple[DecisionOption, ...]:
    options: list[DecisionOption] = [
        DecisionOption(
            option_id=DECLINE_FIGHT_UNIT_GRANT_OPTION_ID,
            label="Decline fight unit grant",
            payload=validate_json_value(
                {
                    "submission_kind": SELECT_FIGHT_UNIT_GRANT_DECISION_TYPE,
                    "unit_instance_id": activation.unit_instance_id,
                    "activation_request_id": activation.request_id,
                    "activation_result_id": activation.result_id,
                    "selected_fight_unit_grants": [],
                }
            ),
        )
    ]
    for grant in grants:
        options.append(
            DecisionOption(
                option_id=grant.hook_id,
                label=grant.label,
                payload=validate_json_value(
                    {
                        "submission_kind": SELECT_FIGHT_UNIT_GRANT_DECISION_TYPE,
                        "unit_instance_id": activation.unit_instance_id,
                        "activation_request_id": activation.request_id,
                        "activation_result_id": activation.result_id,
                        "selected_fight_unit_grants": [grant.to_payload()],
                    }
                ),
            )
        )
    return tuple(options)


def _apply_fight_unit_selected_grant_decision(
    *,
    state: GameState,
    result: DecisionResult,
    decisions: DecisionController,
    registry: FightUnitSelectedGrantRegistry,
) -> LifecycleStatus | None:
    _validate_fight_phase_state(state)
    fight_state = _require_fight_state(state)
    activation = fight_state.active_activation
    if activation is None:
        raise GameLifecycleError("Fight unit grant requires an active activation.")
    if result.actor_id != activation.player_id:
        raise GameLifecycleError("Fight unit grant actor must match activation player.")
    payload = _decision_payload_object(result.payload)
    _validate_fight_unit_selected_grant_payload_context(payload=payload, activation=activation)
    if result.selected_option_id == DECLINE_FIGHT_UNIT_GRANT_OPTION_ID:
        selected_grants: tuple[FightUnitSelectedGrant, ...] = ()
    else:
        selected_grants = _selected_fight_unit_grants_from_payload(payload)
        _validate_selected_fight_unit_grants(
            state=state,
            activation=activation,
            registry=registry,
            selected_grants=selected_grants,
        )
    persisting_effects = tuple(
        effect
        for grant in selected_grants
        for effect in _record_fight_unit_selected_grant_effects(
            state=state,
            result=result,
            activation=activation,
            grant=grant,
        )
    )
    decisions.event_log.append(
        "fight_unit_selected_grant_decision_resolved",
        validate_json_value(
            {
                "game_id": state.game_id,
                "battle_round": state.battle_round,
                "phase": BattlePhase.FIGHT.value,
                "active_player_id": state.active_player_id,
                "player_id": activation.player_id,
                "unit_instance_id": activation.unit_instance_id,
                "request_id": result.request_id,
                "result_id": result.result_id,
                "selected_option_id": result.selected_option_id,
                "selected_fight_unit_grants": [grant.to_payload() for grant in selected_grants],
                "persisting_effects": [effect.to_payload() for effect in persisting_effects],
                "phase_body_status": "fight_unit_selected_grant_decision_resolved",
            }
        ),
    )
    return None


def _selected_fight_unit_grants_from_payload(
    payload: dict[str, JsonValue],
) -> tuple[FightUnitSelectedGrant, ...]:
    raw_grants = payload.get("selected_fight_unit_grants")
    if not isinstance(raw_grants, list):
        raise GameLifecycleError("Fight unit grant payload missing selected grants.")
    raw_grant_payloads = cast(list[object], raw_grants)
    grants: list[FightUnitSelectedGrant] = []
    for raw_grant in raw_grant_payloads:
        if not isinstance(raw_grant, dict):
            raise GameLifecycleError("Fight unit selected grants must be objects.")
        grants.append(
            FightUnitSelectedGrant.from_payload(cast(FightUnitSelectedGrantPayload, raw_grant))
        )
    return tuple(sorted(grants, key=lambda grant: grant.hook_id))


def _validate_selected_fight_unit_grants(
    *,
    state: GameState,
    activation: FightActivationSelection,
    registry: FightUnitSelectedGrantRegistry,
    selected_grants: tuple[FightUnitSelectedGrant, ...],
) -> None:
    if not selected_grants:
        raise GameLifecycleError("Fight unit grant selection requires a selected grant.")
    available_payloads = {
        grant.hook_id: grant.to_payload()
        for grant in registry.grants_for(
            _fight_unit_selected_context(state=state, activation=activation)
        )
    }
    for grant in selected_grants:
        expected = available_payloads.get(grant.hook_id)
        if expected is None:
            raise GameLifecycleError("Selected fight unit grant is not available.")
        if grant.to_payload() != expected:
            raise GameLifecycleError("Selected fight unit grant payload drift.")


def _record_fight_unit_selected_grant_effects(
    *,
    state: GameState,
    result: DecisionResult,
    activation: FightActivationSelection,
    grant: FightUnitSelectedGrant,
) -> tuple[PersistingEffect, ...]:
    effects: list[PersistingEffect] = []
    if grant.decision_effect_payload is not None:
        resource_spend_result = apply_faction_resource_spend_effect(
            state=state,
            player_id=activation.player_id,
            source_id=f"{grant.source_id}:{result.request_id}:{result.result_id}:spend",
            effect_payload=grant.decision_effect_payload,
        )
        spend_effect = PersistingEffect(
            effect_id=f"{result.result_id}:{grant.hook_id}:decision",
            source_rule_id=grant.source_id,
            owner_player_id=activation.player_id,
            target_unit_instance_ids=(activation.unit_instance_id,),
            started_battle_round=state.battle_round,
            started_phase=BattlePhaseKind.FIGHT,
            expiration=EffectExpiration.end_battle_round(battle_round=state.battle_round),
            effect_payload=faction_resource_result_enriched_payload(
                effect_payload=grant.decision_effect_payload,
                result=resource_spend_result,
            ),
        )
        state.record_persisting_effect(spend_effect)
        effects.append(spend_effect)
    if grant.unit_effect_payload is None:
        if not effects:
            raise GameLifecycleError("Fight unit selected grant has no effect to record.")
        return tuple(effects)
    unit_effect = PersistingEffect(
        effect_id=f"{result.result_id}:{grant.hook_id}:unit",
        source_rule_id=grant.source_id,
        owner_player_id=activation.player_id,
        target_unit_instance_ids=_fight_unit_selected_grant_unit_effect_target_ids(
            unit_instance_id=activation.unit_instance_id,
            effect_payload=grant.unit_effect_payload,
        ),
        started_battle_round=state.battle_round,
        started_phase=BattlePhaseKind.FIGHT,
        expiration=_fight_unit_selected_grant_effect_expiration(
            state=state,
            activation=activation,
            grant=grant,
        ),
        effect_payload=grant.unit_effect_payload,
    )
    state.record_persisting_effect(unit_effect)
    effects.append(unit_effect)
    return tuple(effects)


def _fight_unit_selected_context(
    *,
    state: GameState,
    activation: FightActivationSelection,
) -> FightUnitSelectedContext:
    return FightUnitSelectedContext(
        state=state,
        player_id=activation.player_id,
        battle_round=activation.battle_round,
        unit_instance_id=activation.unit_instance_id,
        fight_type=activation.fight_type.value,
        ordering_band=activation.ordering_band.value,
        request_id=activation.request_id,
        result_id=activation.result_id,
    )


def _validate_fight_unit_selected_grant_payload_context(
    *,
    payload: dict[str, JsonValue],
    activation: FightActivationSelection,
) -> None:
    if _payload_string(payload, key="submission_kind") != SELECT_FIGHT_UNIT_GRANT_DECISION_TYPE:
        raise GameLifecycleError("Fight unit grant payload has invalid submission_kind.")
    if _payload_string(payload, key="unit_instance_id") != activation.unit_instance_id:
        raise GameLifecycleError("Fight unit grant unit drift.")
    if (
        _payload_string(payload, key="activation_request_id") != activation.request_id
        or _payload_string(payload, key="activation_result_id") != activation.result_id
    ):
        raise GameLifecycleError("Fight unit grant activation decision drift.")


def _fight_unit_selected_grant_unit_effect_target_ids(
    *,
    unit_instance_id: str,
    effect_payload: JsonValue,
) -> tuple[str, ...]:
    if not isinstance(effect_payload, dict):
        return (_validate_identifier("unit_instance_id", unit_instance_id),)
    raw_target_ids = effect_payload.get("target_unit_instance_ids")
    if raw_target_ids is None:
        return (_validate_identifier("unit_instance_id", unit_instance_id),)
    if not isinstance(raw_target_ids, list):
        raise GameLifecycleError("Fight unit grant target_unit_instance_ids must be a list.")
    target_ids = tuple(
        _validate_identifier("target_unit_instance_ids", raw_id) for raw_id in raw_target_ids
    )
    if not target_ids:
        raise GameLifecycleError("Fight unit grant target_unit_instance_ids is empty.")
    if len(set(target_ids)) != len(target_ids):
        raise GameLifecycleError("Fight unit grant target_unit_instance_ids are duplicated.")
    return target_ids


def _fight_unit_selected_grant_effect_expiration(
    *,
    state: GameState,
    activation: FightActivationSelection,
    grant: FightUnitSelectedGrant,
) -> EffectExpiration:
    expiration = grant.unit_effect_expiration
    if expiration == "end_phase":
        return EffectExpiration.end_phase(
            battle_round=state.battle_round,
            phase=BattlePhaseKind.FIGHT,
            player_id=_active_player_id(state),
        )
    if expiration == "end_turn":
        return EffectExpiration.end_turn(
            battle_round=state.battle_round,
            player_id=activation.player_id,
        )
    raise GameLifecycleError("Fight unit grant has unsupported expiration.")


def _apply_fight_dice_reroll_decision(
    *,
    state: GameState,
    result: DecisionResult,
    decisions: DecisionController,
) -> LifecycleStatus | None:
    _validate_fight_phase_state(state)
    fight_state = _require_fight_state(state)
    attack_sequence = fight_state.attack_sequence
    if attack_sequence is None:
        raise GameLifecycleError("Fight dice reroll requires an active attack sequence.")
    apply_source_backed_attack_dice_reroll_decision(
        state=state,
        result=result,
        decisions=decisions,
        attack_sequence=attack_sequence,
        expected_phase=BattlePhase.FIGHT,
        phase_label="Fight",
    )
    return None


def _apply_fight_activation_ability_decision(
    *,
    state: GameState,
    result: DecisionResult,
    decisions: DecisionController,
) -> LifecycleStatus | None:
    fight_state = _require_fight_state(state)
    activation = fight_state.active_activation
    if activation is None:
        raise GameLifecycleError("Fight activation ability requires active activation.")
    if result.selected_option_id == DECLINE_FIGHT_ACTIVATION_ABILITY_OPTION_ID:
        if not is_fight_activation_ability_decline_payload(result.payload):
            raise GameLifecycleError("Fight activation ability decline payload drift.")
        decisions.event_log.append(
            "fight_activation_ability_declined",
            validate_json_value(
                {
                    "game_id": state.game_id,
                    "battle_round": state.battle_round,
                    "phase": BattlePhase.FIGHT.value,
                    "phase_body_status": _FIGHT_ACTIVATION_ABILITY_DECLINED_STATUS,
                    "request_id": result.request_id,
                    "result_id": result.result_id,
                    "activation_result_id": activation.result_id,
                    "result_payload": result.payload,
                }
            ),
        )
        return None
    ability_use = fight_activation_ability_use_from_result(
        payload=result.payload,
        request_id=result.request_id,
        result_id=result.result_id,
    )
    if ability_use.activation_result_id != activation.result_id:
        raise GameLifecycleError("Fight activation ability use activation result drift.")
    if ability_use.activation_request_id != activation.request_id:
        raise GameLifecycleError("Fight activation ability use activation request drift.")
    if ability_use.unit_instance_id != activation.unit_instance_id:
        raise GameLifecycleError("Fight activation ability use target unit drift.")
    if ability_use.player_id != activation.player_id:
        raise GameLifecycleError("Fight activation ability use player drift.")
    ability_use_payload = cast(
        dict[str, JsonValue],
        validate_json_value(cast(JsonValue, ability_use.to_payload())),
    )
    effect = PersistingEffect(
        effect_id=(
            f"{ability_use.result_id}:{ability_use.ability_id}:"
            f"{_fight_activation_effect_id_suffix(ability_use.effect_kind)}"
        ),
        source_rule_id=ability_use.source_id,
        owner_player_id=ability_use.player_id,
        target_unit_instance_ids=(ability_use.unit_instance_id,),
        started_battle_round=state.battle_round,
        started_phase=BattlePhase.FIGHT,
        expiration=EffectExpiration.end_phase(
            battle_round=state.battle_round,
            phase=BattlePhase.FIGHT,
            player_id=_active_player_id(state),
        ),
        effect_payload={
            **ability_use_payload,
            "effect_kind": ability_use.effect_kind,
        },
    )
    state.record_persisting_effect(effect)
    spend_effect = None
    if ability_use.decision_effect_payload is not None:
        spend_effect = PersistingEffect(
            effect_id=f"{ability_use.result_id}:{ability_use.ability_id}:decision",
            source_rule_id=ability_use.source_id,
            owner_player_id=ability_use.player_id,
            target_unit_instance_ids=(ability_use.unit_instance_id,),
            started_battle_round=state.battle_round,
            started_phase=BattlePhase.FIGHT,
            expiration=EffectExpiration.end_battle_round(battle_round=state.battle_round),
            effect_payload=ability_use.decision_effect_payload,
        )
        state.record_persisting_effect(spend_effect)
    decisions.event_log.append(
        "fight_activation_ability_used",
        validate_json_value(
            {
                "game_id": state.game_id,
                "battle_round": state.battle_round,
                "phase": BattlePhase.FIGHT.value,
                "phase_body_status": _FIGHT_ACTIVATION_ABILITY_USED_STATUS,
                "request_id": result.request_id,
                "result_id": result.result_id,
                "activation_result_id": activation.result_id,
                "ability_use": ability_use_payload,
                "persisting_effect": effect.to_payload(),
                "decision_persisting_effect": (
                    None if spend_effect is None else spend_effect.to_payload()
                ),
            }
        ),
    )
    return None


def _apply_fight_interrupt_decision(
    *,
    state: GameState,
    result: DecisionResult,
    decisions: DecisionController,
    policy: FightPolicyDescriptor,
) -> LifecycleStatus | None:
    del policy
    fight_state = _require_fight_state(state)
    interrupt = fight_interrupt_request_from_payload(result.payload)
    if result.selected_option_id == DECLINE_FIGHT_INTERRUPT_OPTION_ID:
        state.replace_fight_phase_state(
            fight_state.with_resolved_interrupt(
                interrupt_id=interrupt.interrupt_id,
                source_effect_id=interrupt.source_effect_id,
            )
        )
        decisions.event_log.append(
            "fight_interrupt_declined",
            validate_json_value(
                {
                    "game_id": state.game_id,
                    "battle_round": state.battle_round,
                    "phase": BattlePhase.FIGHT.value,
                    "phase_body_status": _FIGHT_INTERRUPT_DECLINED_STATUS,
                    "interrupt": interrupt.to_payload(),
                }
            ),
        )
        return None

    selection = current_fight_activation_selection_from_payload(
        result_payload=result.payload,
        request_id=result.request_id,
        result_id=result.result_id,
        interrupt_id=interrupt.interrupt_id,
    )
    state.replace_fight_phase_state(
        fight_state.with_activation(selection)
        .with_resolved_interrupt(
            interrupt_id=interrupt.interrupt_id,
            source_effect_id=interrupt.source_effect_id,
        )
        .with_active_activation(selection)
    )
    decisions.event_log.append(
        "fight_interrupt_activation_selected",
        validate_json_value(
            {
                "game_id": state.game_id,
                "battle_round": state.battle_round,
                "phase": BattlePhase.FIGHT.value,
                "phase_body_status": _FIGHT_INTERRUPT_RECORDED_STATUS,
                "interrupt": interrupt.to_payload(),
                "activation_selection": selection.to_payload(),
            }
        ),
    )
    return None


def _request_counteroffensive_if_available(
    *,
    handler: FightPhaseHandler,
    state: GameState,
    decisions: DecisionController,
    reaction_queue: ReactionQueue | None,
    fought_selection: FightActivationSelection,
    trigger_event_id: str,
    policy: FightPolicyDescriptor,
) -> LifecycleStatus | None:
    if reaction_queue is None:
        return None
    for player_id in state.player_ids:
        if player_id == fought_selection.player_id:
            continue
        contexts = eligible_fight_contexts_for_player(
            state=state,
            fight_state=_require_fight_state(state),
            player_id=player_id,
            policy=policy,
        )
        if not contexts:
            continue
        window_id = (
            f"counteroffensive-round-{state.battle_round:02d}-"
            f"after-{fought_selection.unit_instance_id}-player-{player_id}"
        )
        trigger_payload = validate_json_value(
            {
                "fought_unit_instance_id": fought_selection.unit_instance_id,
                "fought_selection": fought_selection.to_payload(),
                "trigger_event_id": trigger_event_id,
                "eligible_unit_instance_ids": [context.unit_instance_id for context in contexts],
            }
        )
        context = StratagemEligibilityContext.from_state(
            state=state,
            player_id=player_id,
            trigger_kind=TimingTriggerKind.JUST_AFTER_ENEMY_UNIT_HAS_FOUGHT,
            timing_window_id=window_id,
            trigger_payload=trigger_payload,
        )
        if stratagem_window_declined_for_context(decisions=decisions, context=context):
            continue
        proposal = stratagem_target_proposal_from_index(
            state=state,
            index=handler.stratagem_index,
            context=context,
            handler_id=CORE_COUNTEROFFENSIVE_HANDLER_ID,
        )
        if proposal is None:
            continue
        reaction_window = ReactionWindow(
            timing_window=TimingWindow(
                window_id=window_id,
                descriptor=TimingWindowDescriptor(
                    descriptor_id="core-counteroffensive-after-enemy-fought",
                    trigger_kind=TimingTriggerKind.JUST_AFTER_ENEMY_UNIT_HAS_FOUGHT,
                    source_rule_id=CORE_COUNTEROFFENSIVE_HANDLER_ID,
                    phase=BattlePhase.FIGHT,
                    source_step="fight",
                    metadata=trigger_payload,
                ),
                game_id=state.game_id,
                battle_round=state.battle_round,
                active_player_id=_active_player_id(state),
                phase=BattlePhase.FIGHT,
                trigger_event_id=trigger_event_id,
            ),
            eligible_player_ids=(player_id,),
        )
        triggered = reaction_queue.emit_decision_request(
            state=state,
            decisions=decisions,
            reaction_window=reaction_window,
            parent_phase=BattlePhase.FIGHT,
            parent_step="fight",
            resume_token=f"{window_id}-resume",
            actor_id=player_id,
            decision_type=STRATAGEM_TARGET_PROPOSAL_DECISION_TYPE,
            options=(parameterized_decision_option(),),
            payload_factory=_stratagem_target_proposal_payload_factory(proposal),
        )
        return LifecycleStatus.waiting_for_decision(
            stage=GameLifecycleStage.BATTLE,
            decision_request=triggered.decision_request,
            payload={
                "phase": BattlePhase.FIGHT.value,
                "phase_body_status": "counteroffensive_reaction_pending",
                "request_id": triggered.decision_request.request_id,
                "reacting_player_id": player_id,
            },
        )
    return None


def _request_epic_challenge_if_available(
    *,
    handler: FightPhaseHandler,
    state: GameState,
    decisions: DecisionController,
    activation: FightActivationSelection,
) -> LifecycleStatus | None:
    unit = _unit_by_id(state=state, unit_instance_id=activation.unit_instance_id)
    if not _unit_has_keyword(unit, "CHARACTER"):
        return None
    window_id = f"epic-challenge-round-{state.battle_round:02d}-unit-{activation.unit_instance_id}"
    trigger_payload = validate_json_value(
        {
            "selected_unit_instance_id": activation.unit_instance_id,
            "activation_selection": activation.to_payload(),
        }
    )
    context = StratagemEligibilityContext.from_state(
        state=state,
        player_id=activation.player_id,
        trigger_kind=TimingTriggerKind.JUST_AFTER_FRIENDLY_UNIT_SELECTED_TO_FIGHT,
        timing_window_id=window_id,
        trigger_payload=trigger_payload,
    )
    if stratagem_window_declined_for_context(decisions=decisions, context=context):
        return None
    proposal = stratagem_target_proposal_from_index(
        state=state,
        index=handler.stratagem_index,
        context=context,
        handler_id=CORE_EPIC_CHALLENGE_HANDLER_ID,
    )
    if proposal is None:
        return None
    return request_stratagem_target_proposal(
        state=state,
        decisions=decisions,
        proposal_request=proposal,
        allow_decline=True,
    )


def _stratagem_target_proposal_payload_factory(
    proposal: StratagemTargetProposal,
) -> Callable[[str, str, str], JsonValue]:
    if type(proposal) is not StratagemTargetProposal:
        raise GameLifecycleError(
            "Stratagem target proposal payload factory requires a StratagemTargetProposal."
        )

    def payload_factory(request_id: str, decision_type: str, actor_id: str) -> JsonValue:
        return stratagem_target_proposal_request_payload(
            proposal,
            request_id=request_id,
            decision_type=decision_type,
            actor_id=actor_id,
            allow_decline=True,
        )

    return payload_factory


def _request_fight_interrupt_if_available(
    *,
    state: GameState,
    decisions: DecisionController,
    reaction_queue: ReactionQueue | None,
    fought_selection: FightActivationSelection,
    trigger_event_id: str,
    policy: FightPolicyDescriptor,
) -> LifecycleStatus | None:
    if reaction_queue is None:
        return None
    fight_state = _require_fight_state(state)
    for player_id in state.player_ids:
        if player_id == fought_selection.player_id:
            continue
        for source_effect_id, source_rule_id, _effect_rule_id in fight_interrupt_sources_for_player(
            state=state,
            player_id=player_id,
        ):
            interrupt_id = f"fight-interrupt:{source_effect_id}:{trigger_event_id}"
            if (
                interrupt_id in fight_state.fight_order_state.resolved_interrupt_ids
                or source_effect_id
                in fight_state.fight_order_state.resolved_interrupt_source_effect_ids
            ):
                continue
            contexts = eligible_fight_contexts_for_player(
                state=state,
                fight_state=fight_state,
                player_id=player_id,
                policy=policy,
            )
            if not contexts:
                continue
            interrupt = FightInterruptRequest(
                interrupt_id=interrupt_id,
                source_effect_id=source_effect_id,
                source_rule_id=source_rule_id,
                player_id=player_id,
                battle_round=state.battle_round,
                ordering_band=fight_state.current_ordering_band,
                trigger_event_id=trigger_event_id,
                eligible_unit_ids=tuple(context.unit_instance_id for context in contexts),
            )
            triggered = reaction_queue.emit_decision_request(
                state=state,
                decisions=decisions,
                reaction_window=ReactionWindow(
                    timing_window=TimingWindow(
                        window_id=(
                            f"timing-window:{state.game_id}:round-{state.battle_round:02d}:"
                            f"fight-interrupt:{source_effect_id}:{trigger_event_id}"
                        ),
                        descriptor=TimingWindowDescriptor(
                            descriptor_id=f"{interrupt_id}:descriptor",
                            trigger_kind=TimingTriggerKind.JUST_AFTER_ENEMY_UNIT_HAS_FOUGHT,
                            source_rule_id=source_rule_id,
                            phase=BattlePhase.FIGHT,
                            source_step="fight",
                        ),
                        game_id=state.game_id,
                        battle_round=state.battle_round,
                        active_player_id=_active_player_id(state),
                        phase=BattlePhase.FIGHT,
                        trigger_event_id=trigger_event_id,
                    ),
                    eligible_player_ids=(player_id,),
                ),
                parent_phase=BattlePhase.FIGHT,
                parent_step="fight",
                resume_token=interrupt_id,
                actor_id=player_id,
                decision_type=FIGHT_INTERRUPT_DECISION_TYPE,
                options=_fight_interrupt_options(
                    state=state,
                    fight_state=fight_state,
                    interrupt=interrupt,
                    contexts=contexts,
                    policy=policy,
                ),
                payload={
                    "phase_body_status": _FIGHT_INTERRUPT_REQUIRED_STATUS,
                    "interrupt": validate_json_value(interrupt.to_payload()),
                },
            )
            decisions.event_log.append(
                "fight_interrupt_requested",
                validate_json_value(
                    {
                        "game_id": state.game_id,
                        "battle_round": state.battle_round,
                        "phase": BattlePhase.FIGHT.value,
                        "phase_body_status": _FIGHT_INTERRUPT_REQUIRED_STATUS,
                        "request_id": triggered.decision_request.request_id,
                        "interrupt": interrupt.to_payload(),
                    }
                ),
            )
            return LifecycleStatus.waiting_for_decision(
                stage=GameLifecycleStage.BATTLE,
                decision_request=triggered.decision_request,
                payload={
                    "phase": BattlePhase.FIGHT.value,
                    "phase_body_status": _FIGHT_INTERRUPT_REQUIRED_STATUS,
                    "request_id": triggered.decision_request.request_id,
                    "interrupt_id": interrupt.interrupt_id,
                },
            )
    return None


def _fight_interrupt_options(
    *,
    state: GameState,
    fight_state: FightPhaseState,
    interrupt: FightInterruptRequest,
    contexts: tuple[FightEligibilityContext, ...],
    policy: FightPolicyDescriptor,
) -> tuple[DecisionOption, ...]:
    options = [
        DecisionOption(
            option_id=DECLINE_FIGHT_INTERRUPT_OPTION_ID,
            label="Decline Fight Interrupt",
            payload=decline_fight_interrupt_payload(interrupt=interrupt),
        )
    ]
    for context in contexts:
        for fight_type in legal_fight_types_for_context(context=context, policy=policy):
            options.append(
                DecisionOption(
                    option_id=fight_activation_option_id(
                        unit_instance_id=context.unit_instance_id,
                        fight_type=fight_type,
                    ),
                    label=f"{context.unit_instance_id} interrupt {fight_type.value}",
                    payload=fight_interrupt_option_payload(
                        state=state,
                        fight_state=fight_state,
                        interrupt=interrupt,
                        context=context,
                        fight_type=fight_type,
                    ),
                )
            )
    return tuple(options)


def _invalid_fight_pass_status(
    *,
    state: GameState,
    result: DecisionResult,
    fight_state: FightPhaseState,
    current_contexts: tuple[FightEligibilityContext, ...],
    policy: FightPolicyDescriptor,
) -> LifecycleStatus | None:
    if not eligible_pass_is_available(current_contexts):
        return LifecycleStatus.invalid(
            stage=state.stage,
            message="Eligible-to-fight pass is not currently legal.",
            payload={
                "invalid_reason": "invalid_fight_activation_result",
                "field": "eligible_to_fight_pass",
            },
        )
    eligible_pass = current_eligible_pass_from_payload(
        result_payload=result.payload,
        request_id=result.request_id,
        result_id=result.result_id,
    )
    expected_unit_ids = tuple(context.unit_instance_id for context in current_contexts)
    if eligible_pass.eligible_unit_ids != tuple(sorted(expected_unit_ids)):
        return LifecycleStatus.invalid(
            stage=state.stage,
            message="Eligible-to-fight pass unit snapshot is stale.",
            payload={
                "invalid_reason": "invalid_fight_activation_result",
                "field": "eligible_unit_ids",
            },
        )
    if eligible_pass.player_id != fight_state.fight_order_state.next_player_id:
        return LifecycleStatus.invalid(
            stage=state.stage,
            message="Eligible-to-fight pass player drifted.",
            payload={
                "invalid_reason": "invalid_fight_activation_result",
                "field": "player_id",
            },
        )
    if eligible_pass.pass_distance_inches != policy.eligible_pass_distance_inches:
        return LifecycleStatus.invalid(
            stage=state.stage,
            message="Eligible-to-fight pass distance drifted.",
            payload={
                "invalid_reason": "invalid_fight_activation_result",
                "field": "pass_distance_inches",
            },
        )
    return None


def _invalid_fight_activation_selection_status(
    *,
    state: GameState,
    result: DecisionResult,
    fight_state: FightPhaseState,
    current_contexts: tuple[FightEligibilityContext, ...],
    policy: FightPolicyDescriptor,
) -> LifecycleStatus | None:
    selected = current_fight_activation_selection_from_payload(
        result_payload=result.payload,
        request_id=result.request_id,
        result_id=result.result_id,
    )
    expected_option_id = fight_activation_option_id(
        unit_instance_id=selected.unit_instance_id,
        fight_type=selected.fight_type,
    )
    if result.selected_option_id != expected_option_id:
        return LifecycleStatus.invalid(
            stage=state.stage,
            message="Fight activation selected option does not match its payload.",
            payload={
                "invalid_reason": "invalid_fight_activation_result",
                "field": "selected_option_id",
            },
        )
    if selected.player_id != fight_state.fight_order_state.next_player_id:
        return LifecycleStatus.invalid(
            stage=state.stage,
            message="Fight activation player drifted.",
            payload={
                "invalid_reason": "invalid_fight_activation_result",
                "field": "player_id",
            },
        )
    if selected.ordering_band is not fight_state.current_ordering_band:
        return LifecycleStatus.invalid(
            stage=state.stage,
            message="Fight activation ordering band drifted.",
            payload={
                "invalid_reason": "invalid_fight_activation_result",
                "field": "ordering_band",
            },
        )
    if selected.fight_type not in policy.fight_types:
        return LifecycleStatus.invalid(
            stage=state.stage,
            message="Fight activation selected unsupported fight type.",
            payload={
                "invalid_reason": "invalid_fight_activation_result",
                "field": "fight_type",
            },
        )
    matching_context = _matching_context(current_contexts, selected.unit_instance_id)
    if matching_context is None:
        return LifecycleStatus.invalid(
            stage=state.stage,
            message="Fight activation selected unit is no longer eligible.",
            payload={
                "invalid_reason": "invalid_fight_activation_result",
                "field": "unit_instance_id",
            },
        )
    if matching_context.to_payload() != _context_payload_from_result(result):
        return LifecycleStatus.invalid(
            stage=state.stage,
            message="Fight activation eligibility context is stale.",
            payload={
                "invalid_reason": "invalid_fight_activation_result",
                "field": "eligibility_context",
            },
        )
    if selected.fight_type not in legal_fight_types_for_context(
        context=matching_context,
        policy=policy,
    ):
        return LifecycleStatus.invalid(
            stage=state.stage,
            message="Fight type is not legal for the selected unit.",
            payload={
                "invalid_reason": "invalid_fight_activation_result",
                "field": "fight_type",
            },
        )
    return None


def _matching_context(
    contexts: tuple[FightEligibilityContext, ...],
    unit_instance_id: str,
) -> FightEligibilityContext | None:
    requested_unit_id = _validate_identifier("unit_instance_id", unit_instance_id)
    for context in contexts:
        if context.unit_instance_id == requested_unit_id:
            return context
    return None


def _context_payload_from_result(result: DecisionResult) -> dict[str, JsonValue]:
    payload = result.payload
    if not isinstance(payload, dict):
        raise GameLifecycleError("Fight result payload must be an object.")
    context = payload.get("eligibility_context")
    if not isinstance(context, dict):
        raise GameLifecycleError("Fight result payload requires eligibility_context.")
    return context


def _decision_payload_object(payload: JsonValue) -> dict[str, JsonValue]:
    if not isinstance(payload, dict):
        raise GameLifecycleError("Fight decision payload must be an object.")
    return payload


def _invalid_finite_decision_status(
    *,
    state: GameState,
    request: DecisionRequest,
    result: DecisionResult,
    invalid_reason: str,
) -> LifecycleStatus | None:
    if result.request_id != request.request_id:
        return LifecycleStatus.invalid(
            stage=state.stage,
            message="Decision result does not match the pending request.",
            payload={"invalid_reason": invalid_reason, "field": "request_id"},
        )
    if result.decision_type != request.decision_type:
        return LifecycleStatus.invalid(
            stage=state.stage,
            message="Decision result type does not match the pending request.",
            payload={"invalid_reason": invalid_reason, "field": "decision_type"},
        )
    if result.actor_id != request.actor_id:
        return LifecycleStatus.invalid(
            stage=state.stage,
            message="Decision result actor does not match the pending request.",
            payload={"invalid_reason": invalid_reason, "field": "actor_id"},
        )
    if result.selected_option_id not in {option.option_id for option in request.options}:
        return LifecycleStatus.invalid(
            stage=state.stage,
            message="Decision result selected option is not pending.",
            payload={"invalid_reason": invalid_reason, "field": "selected_option_id"},
        )
    selected_payload = next(
        option.payload
        for option in request.options
        if option.option_id == result.selected_option_id
    )
    if result.payload != selected_payload:
        return LifecycleStatus.invalid(
            stage=state.stage,
            message="Decision result payload does not match the selected option.",
            payload={"invalid_reason": invalid_reason, "field": "payload"},
        )
    return None


def _fight_phase_status_payload(
    *,
    state: GameState,
    fight_state: FightPhaseState,
    phase_body_status: str,
) -> JsonValue:
    return validate_json_value(
        {
            "game_id": state.game_id,
            "battle_round": state.battle_round,
            "active_player_id": fight_state.active_player_id,
            "phase": BattlePhase.FIGHT.value,
            "phase_body_status": phase_body_status,
            "fight_phase_state": fight_state.to_payload(),
        }
    )


def _validate_fight_phase_state(state: GameState) -> None:
    if state.stage is not GameLifecycleStage.BATTLE:
        raise GameLifecycleError("FightPhaseHandler can run only during battle.")
    if state.current_battle_phase is not BattlePhase.FIGHT:
        raise GameLifecycleError("FightPhaseHandler phase does not match state.")
    if state.battlefield_state is None:
        raise GameLifecycleError("FightPhaseHandler requires battlefield_state.")


def _fight_policy_for_handler(handler: FightPhaseHandler) -> FightPolicyDescriptor:
    if handler.ruleset_descriptor is None:
        return RulesetDescriptor.warhammer_40000_eleventh().fight_policy
    return handler.ruleset_descriptor.fight_policy


def _ruleset_descriptor_for_handler(handler: FightPhaseHandler) -> RulesetDescriptor:
    if handler.ruleset_descriptor is None:
        return RulesetDescriptor.warhammer_40000_eleventh()
    return handler.ruleset_descriptor


def _army_catalog_for_handler(handler: FightPhaseHandler) -> ArmyCatalog:
    if handler.army_catalog is None:
        return ArmyCatalog.phase9a_canonical_content_pack()
    return handler.army_catalog


def _require_fight_state(state: GameState) -> FightPhaseState:
    fight_state = state.fight_phase_state
    if fight_state is None:
        raise GameLifecycleError("Fight phase decision requires fight_phase_state.")
    return fight_state


def _require_actor(result: DecisionResult) -> str:
    if result.actor_id is None:
        raise GameLifecycleError("Fight decision requires an actor.")
    return result.actor_id


def _active_player_id(state: GameState) -> str:
    if state.active_player_id is None:
        raise GameLifecycleError("Fight phase requires an active player.")
    return state.active_player_id


def _unit_has_keyword(unit: UnitInstance, keyword: str) -> bool:
    canonical = _canonical_keyword(keyword)
    return canonical in {_canonical_keyword(unit_keyword) for unit_keyword in unit.keywords}


def _canonical_keyword(keyword: str) -> str:
    if type(keyword) is not str:
        raise GameLifecycleError("Unit keyword must be a string.")
    stripped = keyword.strip()
    if not stripped:
        raise GameLifecycleError("Unit keyword must not be empty.")
    return stripped.upper().replace(" ", "_").replace("-", "_")


def _next_player_id(*, player_ids: tuple[str, ...], current_player_id: str) -> str:
    current = _validate_identifier("current_player_id", current_player_id)
    if current not in player_ids:
        raise GameLifecycleError("Fight ordering player is not in this game.")
    index = player_ids.index(current)
    return player_ids[(index + 1) % len(player_ids)]


_validate_identifier = IdentifierValidator(GameLifecycleError)
