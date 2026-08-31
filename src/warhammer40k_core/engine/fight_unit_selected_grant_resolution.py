from __future__ import annotations

from typing import cast

from warhammer40k_core.core.dice import D3RollResult, D3RollResultPayload, DiceRollSpecError
from warhammer40k_core.core.ruleset_descriptor import BattlePhaseKind
from warhammer40k_core.core.validation import IdentifierValidator
from warhammer40k_core.engine.damage_allocation import (
    MortalWoundApplication,
    MortalWoundApplicationProgress,
    MortalWoundRoutingResult,
    continue_mortal_wound_application,
)
from warhammer40k_core.engine.decision_controller import DecisionController
from warhammer40k_core.engine.decision_result import DecisionResult
from warhammer40k_core.engine.destruction_provenance import DestructionSourceKind
from warhammer40k_core.engine.dice import DiceRollManager
from warhammer40k_core.engine.effects import (
    GENERIC_RULE_EFFECT_KIND,
    EffectExpiration,
    PersistingEffect,
)
from warhammer40k_core.engine.event_log import JsonValue, validate_json_value
from warhammer40k_core.engine.faction_resources import (
    apply_faction_resource_spend_effect,
    faction_resource_result_enriched_payload,
    resolve_faction_resource_refund_roll,
    validate_faction_resource_spend_effect_payload,
)
from warhammer40k_core.engine.fight_order import FightActivationSelection
from warhammer40k_core.engine.fight_unit_selected_hooks import FightUnitSelectedGrant
from warhammer40k_core.engine.game_state import GameState
from warhammer40k_core.engine.model_destruction_cause_authority import (
    ModelDestructionCauseKind,
)
from warhammer40k_core.engine.mortal_wound_destruction_evidence import (
    MortalWoundDestructionEvidence,
    MortalWoundDestructionEvidencePayload,
)
from warhammer40k_core.engine.mortal_wound_feel_no_pain_hooks import (
    MortalWoundFeelNoPainContinuationContext,
)
from warhammer40k_core.engine.mortal_wound_logical_death import (
    MortalWoundLogicalDeathCauseBinding,
    fixed_mortal_wound_logical_death_recorder,
)
from warhammer40k_core.engine.mortal_wound_model_allocation import (
    mortal_wound_resolution_progress,
    resolve_mortal_wound_decision,
)
from warhammer40k_core.engine.phase import (
    BattlePhase,
    GameLifecycleError,
    GameLifecycleStage,
    LifecycleStatus,
)
from warhammer40k_core.engine.rule_model_destruction_applied_damage import (
    continue_applied_mortal_wound_destruction_with_rule_reactions,
)
from warhammer40k_core.engine.rules_units import rules_unit_view_by_id
from warhammer40k_core.rules.rule_ir import RuleEffectKind, RuleTargetKind

SELECTED_TO_FIGHT_SELF_MORTAL_WOUNDS_SOURCE_KIND = (
    "generic_rule_selected_to_fight_self_mortal_wounds"
)
SELECTED_TO_FIGHT_SELF_MORTAL_WOUNDS_D3_ROLL_TYPE = (
    "generic_rule.selected_to_fight.self_mortal_wounds.d3"
)
SELECTED_TO_FIGHT_SELF_MORTAL_WOUNDS_PENDING_EVENT = (
    "generic_rule_selected_to_fight_self_mortal_wounds_pending"
)
SELECTED_TO_FIGHT_SELF_MORTAL_WOUNDS_RESOLVED_EVENT = (
    "generic_rule_selected_to_fight_self_mortal_wounds_resolved"
)


def record_fight_unit_selected_grant_effects(
    *,
    state: GameState,
    decisions: DecisionController,
    result: DecisionResult,
    activation: FightActivationSelection,
    grant: FightUnitSelectedGrant,
) -> tuple[PersistingEffect, ...]:
    if type(state) is not GameState:
        raise GameLifecycleError("Fight-unit-selected grant effects require GameState.")
    if type(decisions) is not DecisionController:
        raise GameLifecycleError("Fight-unit-selected grant effects require decisions.")
    if type(result) is not DecisionResult:
        raise GameLifecycleError("Fight-unit-selected grant effects require result.")
    if type(activation) is not FightActivationSelection:
        raise GameLifecycleError("Fight-unit-selected grant effects require activation.")
    if type(grant) is not FightUnitSelectedGrant:
        raise GameLifecycleError("Fight-unit-selected grant effects require grant.")
    timed_effects = _validated_timed_persisting_effects(
        state=state,
        result=result,
        activation=activation,
        grant=grant,
    )
    if grant.decision_effect_payload is not None:
        validate_faction_resource_spend_effect_payload(grant.decision_effect_payload)
        unresolved_spend_effect = _resource_spend_persisting_effect(
            state=state,
            result=result,
            activation=activation,
            grant=grant,
            effect_payload=grant.decision_effect_payload,
        )
        _validate_new_persisting_effect(state=state, effect=unresolved_spend_effect)
    effects: list[PersistingEffect] = []
    if grant.decision_effect_payload is not None:
        resource_spend_result = apply_faction_resource_spend_effect(
            state=state,
            player_id=activation.player_id,
            source_id=f"{grant.source_id}:{result.request_id}:{result.result_id}:spend",
            effect_payload=grant.decision_effect_payload,
        )
        if resource_spend_result is None:
            raise GameLifecycleError(
                "Fight-unit-selected decision effect is not a faction resource spend."
            )
        spend_effect = _resource_spend_persisting_effect(
            state=state,
            result=result,
            activation=activation,
            grant=grant,
            effect_payload=faction_resource_result_enriched_payload(
                effect_payload=grant.decision_effect_payload,
                result=resource_spend_result,
            ),
        )
        state.record_persisting_effect(spend_effect)
        resolve_faction_resource_refund_roll(
            state=state,
            decisions=decisions,
            spend_effect=spend_effect,
        )
        effects.append(spend_effect)
    for effect in timed_effects:
        state.record_persisting_effect(effect)
        effects.append(effect)
    if not effects and grant.immediate_effect_payload is None:
        raise GameLifecycleError("Fight-unit-selected grant has no effect to resolve.")
    return tuple(effects)


def validate_fight_unit_selected_grant_effects(
    *,
    state: GameState,
    result: DecisionResult,
    activation: FightActivationSelection,
    grant: FightUnitSelectedGrant,
) -> None:
    if type(state) is not GameState:
        raise GameLifecycleError("Fight-unit-selected grant effects require GameState.")
    if type(result) is not DecisionResult:
        raise GameLifecycleError("Fight-unit-selected grant effects require result.")
    if type(activation) is not FightActivationSelection:
        raise GameLifecycleError("Fight-unit-selected grant effects require activation.")
    if type(grant) is not FightUnitSelectedGrant:
        raise GameLifecycleError("Fight-unit-selected grant effects require grant.")
    _validated_timed_persisting_effects(
        state=state,
        result=result,
        activation=activation,
        grant=grant,
    )
    if grant.decision_effect_payload is not None:
        validate_faction_resource_spend_effect_payload(grant.decision_effect_payload)
        unresolved_spend_effect = _resource_spend_persisting_effect(
            state=state,
            result=result,
            activation=activation,
            grant=grant,
            effect_payload=grant.decision_effect_payload,
        )
        _validate_new_persisting_effect(state=state, effect=unresolved_spend_effect)
    if (
        not grant.timed_effects
        and grant.decision_effect_payload is None
        and grant.immediate_effect_payload is None
    ):
        raise GameLifecycleError("Fight-unit-selected grant has no effect to resolve.")


def validate_fight_unit_selected_grant_immediate_effect(
    *,
    state: GameState,
    activation: FightActivationSelection,
    grant: FightUnitSelectedGrant,
) -> None:
    effect_payload = grant.immediate_effect_payload
    if effect_payload is None:
        return
    payload = _generic_self_mortal_wound_effect_payload(effect_payload)
    if payload.get("execution_id") != grant.source_id:
        raise GameLifecycleError("Fight-unit-selected immediate effect source drift.")
    source_model_id = _source_model_instance_id(payload)
    selected_rules_unit = rules_unit_view_by_id(
        state=state,
        unit_instance_id=activation.unit_instance_id,
    )
    matching_models = tuple(
        model
        for model in selected_rules_unit.own_models
        if model.model_instance_id == source_model_id
    )
    if len(matching_models) != 1:
        raise GameLifecycleError(
            "Fight-unit-selected immediate effect bearer is not in the selected rules unit."
        )
    if not matching_models[0].is_alive:
        raise GameLifecycleError("Fight-unit-selected immediate effect bearer is destroyed.")


def apply_fight_unit_selected_grant_immediate_effect(
    *,
    state: GameState,
    decisions: DecisionController,
    result: DecisionResult,
    activation: FightActivationSelection,
    grant: FightUnitSelectedGrant,
) -> LifecycleStatus | None:
    effect_payload = grant.immediate_effect_payload
    if effect_payload is None:
        return None
    validate_fight_unit_selected_grant_immediate_effect(
        state=state,
        activation=activation,
        grant=grant,
    )
    payload = _generic_self_mortal_wound_effect_payload(effect_payload)
    source_model_id = _source_model_instance_id(payload)
    selected_rules_unit = rules_unit_view_by_id(
        state=state,
        unit_instance_id=activation.unit_instance_id,
    )
    dice_manager = DiceRollManager(state.game_id, event_log=decisions.event_log)
    d3_result = dice_manager.roll_d3(
        reason=f"{grant.label} self-inflicted mortal wounds",
        roll_type=SELECTED_TO_FIGHT_SELF_MORTAL_WOUNDS_D3_ROLL_TYPE,
        actor_id=source_model_id,
    )
    mortal_wounds = d3_result.value + _mortal_wound_modifier(payload)
    destruction_evidence = MortalWoundDestructionEvidence.for_non_attack_state(
        state=state,
        destroying_player_id=activation.player_id,
        source_rules_unit_instance_id=selected_rules_unit.unit_instance_id,
        source_model_instance_id=source_model_id,
        destruction_source_kind=DestructionSourceKind.ABILITY,
        action_phase=BattlePhase.FIGHT,
        source_step="selected_to_fight_self_mortal_wounds",
    )
    source_context = validate_json_value(
        {
            "source_kind": SELECTED_TO_FIGHT_SELF_MORTAL_WOUNDS_SOURCE_KIND,
            "phase": BattlePhase.FIGHT.value,
            "source_rule_id": grant.source_id,
            "hook_id": grant.hook_id,
            "label": grant.label,
            "player_id": activation.player_id,
            "unit_instance_id": selected_rules_unit.unit_instance_id,
            "source_model_instance_id": source_model_id,
            "activation_request_id": activation.request_id,
            "activation_result_id": activation.result_id,
            "grant_request_id": result.request_id,
            "grant_result_id": result.result_id,
            "immediate_effect_payload": payload,
            "d3_result": d3_result.to_payload(),
            "mortal_wounds": mortal_wounds,
            "mortal_wound_destruction_evidence": destruction_evidence.to_payload(),
        }
    )
    application_id = f"{result.result_id}:{grant.hook_id}:self-mortal-wounds"
    logical_death_binding = MortalWoundLogicalDeathCauseBinding.fixed(
        cause_kind=ModelDestructionCauseKind.RULE_EFFECT,
        producer_id=application_id,
    )
    progress = MortalWoundApplicationProgress.start(
        application_id=application_id,
        source_rule_id=grant.source_id,
        source_context=source_context,
        target_unit_instance_id=selected_rules_unit.unit_instance_id,
        defender_player_id=activation.player_id,
        mortal_wounds=mortal_wounds,
        spill_over=False,
        priority_model_ids=(source_model_id,),
        destruction_evidence=None,
        logical_death_cause_binding=logical_death_binding,
    )
    routed = continue_mortal_wound_application(
        state=state,
        decisions=decisions,
        request_id=state.next_decision_request_id(),
        progress=progress,
        dice_manager=dice_manager,
        remove_destroyed_models=False,
        logical_death_recorder=fixed_mortal_wound_logical_death_recorder(
            state=state,
            event_log=decisions.event_log,
            binding=logical_death_binding,
        ),
    )
    return _resolve_routed_self_mortal_wounds(
        state=state,
        decisions=decisions,
        feel_no_pain_result_id=None,
        routed=routed,
    )


def apply_selected_to_fight_self_mortal_wound_feel_no_pain_decision(
    context: MortalWoundFeelNoPainContinuationContext,
) -> LifecycleStatus | None:
    if type(context) is not MortalWoundFeelNoPainContinuationContext:
        raise GameLifecycleError(
            "Selected-to-fight self mortal-wound FNP continuation requires context."
        )
    progress = mortal_wound_resolution_progress(context.request)
    if progress.source_context != context.source_context:
        raise GameLifecycleError("Self mortal-wound FNP source context drift.")
    validate_selected_to_fight_self_mortal_wound_progress(progress)
    logical_death_binding = progress.logical_death_cause_binding
    if logical_death_binding is None:
        raise GameLifecycleError("Self mortal-wound logical-death binding is missing.")
    routed = resolve_mortal_wound_decision(
        state=context.state,
        decisions=context.decisions,
        request=context.request,
        result=context.result,
        next_request_id=context.state.next_decision_request_id(),
        dice_manager=context.dice_manager,
        remove_destroyed_models=False,
        logical_death_recorder=fixed_mortal_wound_logical_death_recorder(
            state=context.state,
            event_log=context.decisions.event_log,
            binding=logical_death_binding,
        ),
    )
    return _resolve_routed_self_mortal_wounds(
        state=context.state,
        decisions=context.decisions,
        feel_no_pain_result_id=context.result.result_id,
        routed=routed,
    )


def _resolve_routed_self_mortal_wounds(
    *,
    state: GameState,
    decisions: DecisionController,
    feel_no_pain_result_id: str | None,
    routed: MortalWoundRoutingResult,
) -> LifecycleStatus | None:
    validate_selected_to_fight_self_mortal_wound_progress(routed.progress)
    source_context = _self_mortal_wound_source_context(routed.progress.source_context)
    if routed.request is not None:
        decisions.request_decision(routed.request)
        decisions.event_log.append(
            SELECTED_TO_FIGHT_SELF_MORTAL_WOUNDS_PENDING_EVENT,
            validate_json_value(
                {
                    **source_context,
                    "feel_no_pain_request_id": routed.request.request_id,
                    "remaining_mortal_wounds": routed.progress.remaining_mortal_wounds,
                }
            ),
        )
        return LifecycleStatus.waiting_for_decision(
            stage=GameLifecycleStage.BATTLE,
            decision_request=routed.request,
            payload={
                "phase": BattlePhase.FIGHT.value,
                "decision_type": routed.request.decision_type,
                "source_rule_id": source_context["source_rule_id"],
                "source_kind": SELECTED_TO_FIGHT_SELF_MORTAL_WOUNDS_SOURCE_KIND,
                "target_unit_instance_id": source_context["unit_instance_id"],
                "source_model_instance_id": source_context["source_model_instance_id"],
                "remaining_mortal_wounds": routed.progress.remaining_mortal_wounds,
            },
        )
    application = routed.application
    if type(application) is not MortalWoundApplication:
        raise GameLifecycleError(
            "Selected-to-fight self mortal wounds did not produce an application."
        )
    resolved_payload: dict[str, JsonValue] = {
        **source_context,
        "mortal_wound_application": validate_json_value(application.to_payload()),
    }
    if feel_no_pain_result_id is not None:
        resolved_payload["feel_no_pain_result_id"] = _validate_identifier(
            "feel_no_pain_result_id",
            feel_no_pain_result_id,
        )
    destroyed_applications = tuple(
        damage for damage in application.applications if damage.destroyed
    )
    if destroyed_applications:
        source_model_id = _validate_identifier(
            "source_model_instance_id",
            source_context.get("source_model_instance_id"),
        )
        if (
            len(destroyed_applications) != 1
            or destroyed_applications[0].model_instance_id != source_model_id
        ):
            raise GameLifecycleError(
                "Selected-to-fight self mortal wounds destroyed an unexpected model."
            )
        rules_unit_id = _validate_identifier(
            "unit_instance_id",
            source_context.get("unit_instance_id"),
        )
        rules_unit = rules_unit_view_by_id(
            state=state,
            unit_instance_id=rules_unit_id,
        )
        destruction = continue_applied_mortal_wound_destruction_with_rule_reactions(
            state=state,
            decisions=decisions,
            damage_application=destroyed_applications[0],
            rules_unit_instance_id=rules_unit_id,
            source_rule_id=routed.progress.source_rule_id,
            source_result_id=routed.progress.application_id,
            completion_event_type=SELECTED_TO_FIGHT_SELF_MORTAL_WOUNDS_RESOLVED_EVENT,
            completion_event_payload=validate_json_value(resolved_payload),
            destruction_evidence=_self_mortal_wound_destruction_evidence(source_context),
            defer_attached_split_until_fight_activation_completion=(
                rules_unit.is_attached_rules_unit
            ),
        )
        return destruction.status
    decisions.event_log.append(
        SELECTED_TO_FIGHT_SELF_MORTAL_WOUNDS_RESOLVED_EVENT,
        validate_json_value(resolved_payload),
    )
    return None


def _generic_self_mortal_wound_effect_payload(value: JsonValue) -> dict[str, JsonValue]:
    if not isinstance(value, dict):
        raise GameLifecycleError("Fight-unit-selected immediate effect must be an object.")
    payload = cast(dict[str, JsonValue], validate_json_value(value))
    if payload.get("effect_kind") != GENERIC_RULE_EFFECT_KIND:
        raise GameLifecycleError("Fight-unit-selected immediate effect kind is unsupported.")
    if _effect_kind(payload) is not RuleEffectKind.INFLICT_MORTAL_WOUNDS:
        raise GameLifecycleError("Fight-unit-selected immediate RuleIR effect is unsupported.")
    target = payload.get("target")
    if not isinstance(target, dict) or target.get("kind") != RuleTargetKind.THIS_MODEL.value:
        raise GameLifecycleError("Fight-unit-selected immediate effect must target this model.")
    parameters = _effect_parameters(payload)
    if parameters.get("mortal_wounds_dice_quantity") != 1:
        raise GameLifecycleError("Self mortal wounds require one die.")
    if parameters.get("mortal_wounds_dice_sides") != 3:
        raise GameLifecycleError("Self mortal wounds require a D3.")
    _mortal_wound_modifier(payload)
    source_id = payload.get("source_id")
    if type(source_id) is not str:
        raise GameLifecycleError("Fight-unit-selected immediate effect requires source_id.")
    _validate_identifier("source_id", source_id)
    execution_id = _validate_identifier("execution_id", payload.get("execution_id"))
    if execution_id == source_id:
        raise GameLifecycleError(
            "Fight-unit-selected execution ID must be distinct from its RuleIR source ID."
        )
    _source_model_instance_id(payload)
    return payload


def _effect_kind(payload: dict[str, JsonValue]) -> RuleEffectKind:
    effect = payload.get("effect")
    if not isinstance(effect, dict):
        raise GameLifecycleError("Generic immediate effect requires an effect object.")
    kind = effect.get("kind")
    if type(kind) is not str:
        raise GameLifecycleError("Generic immediate effect requires effect kind.")
    try:
        return RuleEffectKind(kind)
    except ValueError as exc:
        raise GameLifecycleError("Generic immediate effect kind is unsupported.") from exc


def _effect_parameters(payload: dict[str, JsonValue]) -> dict[str, JsonValue]:
    effect = payload.get("effect")
    if not isinstance(effect, dict):
        raise GameLifecycleError("Generic immediate effect requires an effect object.")
    raw_parameters = effect.get("parameters")
    if not isinstance(raw_parameters, list):
        raise GameLifecycleError("Generic immediate effect parameters must be a list.")
    parameters: dict[str, JsonValue] = {}
    for raw_parameter in raw_parameters:
        if not isinstance(raw_parameter, dict):
            raise GameLifecycleError("Generic immediate effect parameter must be an object.")
        key = raw_parameter.get("key")
        if type(key) is not str:
            raise GameLifecycleError("Generic immediate effect parameter requires key.")
        identifier = _validate_identifier("parameter key", key)
        if identifier in parameters:
            raise GameLifecycleError("Generic immediate effect parameters are duplicated.")
        parameters[identifier] = validate_json_value(raw_parameter.get("value"))
    return parameters


def _mortal_wound_modifier(payload: dict[str, JsonValue]) -> int:
    modifier = _effect_parameters(payload).get("mortal_wounds_modifier")
    if type(modifier) is not int or modifier < 0:
        raise GameLifecycleError("Self mortal-wound modifier must be non-negative.")
    return modifier


def _source_model_instance_id(payload: dict[str, JsonValue]) -> str:
    context = payload.get("context")
    if not isinstance(context, dict):
        raise GameLifecycleError("Generic immediate effect requires execution context.")
    return _validate_identifier(
        "source_model_instance_id",
        context.get("source_model_instance_id"),
    )


def _self_mortal_wound_source_context(value: JsonValue) -> dict[str, JsonValue]:
    if not isinstance(value, dict):
        raise GameLifecycleError("Self mortal-wound source context must be an object.")
    context = cast(dict[str, JsonValue], validate_json_value(value))
    if context.get("source_kind") != SELECTED_TO_FIGHT_SELF_MORTAL_WOUNDS_SOURCE_KIND:
        raise GameLifecycleError("Self mortal-wound source kind drift.")
    if context.get("phase") != BattlePhase.FIGHT.value:
        raise GameLifecycleError("Self mortal-wound source phase drift.")
    for key in (
        "source_rule_id",
        "hook_id",
        "player_id",
        "unit_instance_id",
        "source_model_instance_id",
        "activation_request_id",
        "activation_result_id",
        "grant_request_id",
        "grant_result_id",
    ):
        _validate_identifier(key, context.get(key))
    immediate_payload = _generic_self_mortal_wound_effect_payload(
        context.get("immediate_effect_payload")
    )
    source_rule_id = _validate_identifier("source_rule_id", context.get("source_rule_id"))
    if immediate_payload.get("execution_id") != source_rule_id:
        raise GameLifecycleError("Self mortal-wound execution identity drift.")
    source_model_id = _validate_identifier(
        "source_model_instance_id",
        context.get("source_model_instance_id"),
    )
    if _source_model_instance_id(immediate_payload) != source_model_id:
        raise GameLifecycleError("Self mortal-wound bearer identity drift.")
    mortal_wounds = context.get("mortal_wounds")
    if type(mortal_wounds) is not int or mortal_wounds <= 0:
        raise GameLifecycleError("Self mortal-wound source context has invalid wound count.")
    d3_result = _self_mortal_wound_d3_result(context.get("d3_result"))
    if d3_result.source_d6_result.spec.actor_id != source_model_id:
        raise GameLifecycleError("Self mortal-wound D3 actor drift.")
    if d3_result.source_d6_result.spec.roll_type != (
        f"{SELECTED_TO_FIGHT_SELF_MORTAL_WOUNDS_D3_ROLL_TYPE}.d3_source"
    ):
        raise GameLifecycleError("Self mortal-wound D3 roll type drift.")
    if d3_result.value + _mortal_wound_modifier(immediate_payload) != mortal_wounds:
        raise GameLifecycleError("Self mortal-wound D3 result drift.")
    _self_mortal_wound_destruction_evidence(context)
    return context


def _self_mortal_wound_d3_result(value: JsonValue) -> D3RollResult:
    if not isinstance(value, dict):
        raise GameLifecycleError("Self mortal-wound D3 result must be an object.")
    try:
        return D3RollResult.from_payload(cast(D3RollResultPayload, value))
    except (KeyError, DiceRollSpecError) as exc:
        raise GameLifecycleError("Self mortal-wound D3 result is invalid.") from exc


def _self_mortal_wound_destruction_evidence(
    context: dict[str, JsonValue],
) -> MortalWoundDestructionEvidence:
    raw_evidence = context.get("mortal_wound_destruction_evidence")
    if not isinstance(raw_evidence, dict):
        raise GameLifecycleError("Self mortal-wound destruction evidence must be an object.")
    return MortalWoundDestructionEvidence.from_payload(
        cast(MortalWoundDestructionEvidencePayload, raw_evidence)
    )


def validate_selected_to_fight_self_mortal_wound_progress(
    progress: MortalWoundApplicationProgress,
) -> None:
    if type(progress) is not MortalWoundApplicationProgress:
        raise GameLifecycleError("Self mortal-wound progress is invalid.")
    source_context = _self_mortal_wound_source_context(progress.source_context)
    expected_application_id = (
        f"{source_context['grant_result_id']}:{source_context['hook_id']}:self-mortal-wounds"
    )
    if progress.application_id != expected_application_id:
        raise GameLifecycleError("Self mortal-wound progress application identity drift.")
    if progress.logical_death_cause_binding != MortalWoundLogicalDeathCauseBinding.fixed(
        cause_kind=ModelDestructionCauseKind.RULE_EFFECT,
        producer_id=expected_application_id,
    ):
        raise GameLifecycleError("Self mortal-wound logical-death binding drift.")
    if progress.source_rule_id != source_context["source_rule_id"]:
        raise GameLifecycleError("Self mortal-wound progress source rule drift.")
    if progress.target_unit_instance_id != source_context["unit_instance_id"]:
        raise GameLifecycleError("Self mortal-wound progress target unit drift.")
    if progress.defender_player_id != source_context["player_id"]:
        raise GameLifecycleError("Self mortal-wound progress defender drift.")
    if progress.mortal_wounds != source_context["mortal_wounds"]:
        raise GameLifecycleError("Self mortal-wound progress wound count drift.")
    if progress.spill_over:
        raise GameLifecycleError("Self mortal wounds must not spill over.")
    source_model_id = cast(str, source_context["source_model_instance_id"])
    if progress.priority_model_ids != (source_model_id,):
        raise GameLifecycleError("Self mortal-wound progress bearer priority drift.")
    if progress.destruction_evidence is not None:
        raise GameLifecycleError("Self mortal-wound progress must defer destruction evidence.")
    evidence = _self_mortal_wound_destruction_evidence(source_context)
    if evidence.destroying_player_id != source_context["player_id"]:
        raise GameLifecycleError("Self mortal-wound destruction player drift.")
    if evidence.source_rules_unit_instance_id != source_context["unit_instance_id"]:
        raise GameLifecycleError("Self mortal-wound destruction unit drift.")
    if evidence.source_model_instance_id != source_model_id:
        raise GameLifecycleError("Self mortal-wound destruction model drift.")
    if evidence.destruction_source_kind is not DestructionSourceKind.ABILITY:
        raise GameLifecycleError("Self mortal-wound destruction source kind drift.")
    if evidence.action_phase is not BattlePhase.FIGHT:
        raise GameLifecycleError("Self mortal-wound destruction action phase drift.")
    if evidence.parent_battle_phase is not BattlePhase.FIGHT:
        raise GameLifecycleError("Self mortal-wound destruction parent phase drift.")
    if evidence.source_step != "selected_to_fight_self_mortal_wounds":
        raise GameLifecycleError("Self mortal-wound destruction step drift.")


def _validated_timed_persisting_effects(
    *,
    state: GameState,
    result: DecisionResult,
    activation: FightActivationSelection,
    grant: FightUnitSelectedGrant,
) -> tuple[PersistingEffect, ...]:
    effects = tuple(
        PersistingEffect(
            effect_id=f"{result.result_id}:{grant.hook_id}:unit-{index + 1:02d}",
            source_rule_id=grant.source_id,
            owner_player_id=activation.player_id,
            target_unit_instance_ids=_timed_effect_target_unit_ids(
                state=state,
                unit_instance_id=activation.unit_instance_id,
                effect_payload=timed_effect.effect_payload,
            ),
            started_battle_round=state.battle_round,
            started_phase=BattlePhaseKind.FIGHT,
            expiration=_timed_effect_expiration(
                state=state,
                expiration=timed_effect.expiration,
            ),
            effect_payload=timed_effect.effect_payload,
        )
        for index, timed_effect in enumerate(grant.timed_effects)
    )
    for effect in effects:
        _validate_new_persisting_effect(state=state, effect=effect)
    return effects


def _resource_spend_persisting_effect(
    *,
    state: GameState,
    result: DecisionResult,
    activation: FightActivationSelection,
    grant: FightUnitSelectedGrant,
    effect_payload: JsonValue,
) -> PersistingEffect:
    target_unit_id = rules_unit_view_by_id(
        state=state,
        unit_instance_id=activation.unit_instance_id,
    ).unit_instance_id
    return PersistingEffect(
        effect_id=f"{result.result_id}:{grant.hook_id}:decision",
        source_rule_id=grant.source_id,
        owner_player_id=activation.player_id,
        target_unit_instance_ids=(target_unit_id,),
        started_battle_round=state.battle_round,
        started_phase=BattlePhaseKind.FIGHT,
        expiration=EffectExpiration.end_battle_round(battle_round=state.battle_round),
        effect_payload=effect_payload,
    )


def _validate_new_persisting_effect(*, state: GameState, effect: PersistingEffect) -> None:
    if effect.owner_player_id not in state.player_ids:
        raise GameLifecycleError("Fight-unit-selected effect owner is not in the game.")
    for target_unit_id in effect.target_unit_instance_ids:
        rules_unit_view_by_id(state=state, unit_instance_id=target_unit_id)
    if any(stored.effect_id == effect.effect_id for stored in state.persisting_effects):
        raise GameLifecycleError("Fight-unit-selected PersistingEffect already exists.")


def _timed_effect_target_unit_ids(
    *,
    state: GameState,
    unit_instance_id: str,
    effect_payload: JsonValue,
) -> tuple[str, ...]:
    requested_unit_id = _validate_identifier("unit_instance_id", unit_instance_id)
    if not isinstance(effect_payload, dict):
        return (
            rules_unit_view_by_id(
                state=state,
                unit_instance_id=requested_unit_id,
            ).unit_instance_id,
        )
    raw_target_ids = effect_payload.get("target_unit_instance_ids")
    if raw_target_ids is None:
        return (
            rules_unit_view_by_id(
                state=state,
                unit_instance_id=requested_unit_id,
            ).unit_instance_id,
        )
    if not isinstance(raw_target_ids, list):
        raise GameLifecycleError("Fight-unit-selected timed target IDs must be a list.")
    requested_target_ids = tuple(
        _validate_identifier("target_unit_instance_id", item) for item in raw_target_ids
    )
    if not requested_target_ids:
        raise GameLifecycleError("Fight-unit-selected timed target IDs are empty.")
    target_ids = tuple(
        rules_unit_view_by_id(
            state=state,
            unit_instance_id=target_unit_id,
        ).unit_instance_id
        for target_unit_id in requested_target_ids
    )
    if len(set(target_ids)) != len(target_ids):
        raise GameLifecycleError("Fight-unit-selected timed target IDs are duplicated.")
    return target_ids


def _timed_effect_expiration(
    *,
    state: GameState,
    expiration: str,
) -> EffectExpiration:
    active_player_id = state.active_player_id
    if active_player_id is None:
        raise GameLifecycleError("Fight-unit-selected timed effect requires active player.")
    if expiration == "end_phase":
        return EffectExpiration.end_phase(
            battle_round=state.battle_round,
            phase=BattlePhaseKind.FIGHT,
            player_id=active_player_id,
        )
    if expiration == "end_turn":
        return EffectExpiration.end_turn(
            battle_round=state.battle_round,
            player_id=active_player_id,
        )
    raise GameLifecycleError("Fight-unit-selected timed effect expiration is unsupported.")


_validate_identifier = IdentifierValidator(GameLifecycleError)


__all__ = (
    "SELECTED_TO_FIGHT_SELF_MORTAL_WOUNDS_D3_ROLL_TYPE",
    "SELECTED_TO_FIGHT_SELF_MORTAL_WOUNDS_PENDING_EVENT",
    "SELECTED_TO_FIGHT_SELF_MORTAL_WOUNDS_RESOLVED_EVENT",
    "SELECTED_TO_FIGHT_SELF_MORTAL_WOUNDS_SOURCE_KIND",
    "apply_fight_unit_selected_grant_immediate_effect",
    "apply_selected_to_fight_self_mortal_wound_feel_no_pain_decision",
    "record_fight_unit_selected_grant_effects",
    "validate_fight_unit_selected_grant_effects",
    "validate_fight_unit_selected_grant_immediate_effect",
    "validate_selected_to_fight_self_mortal_wound_progress",
)
