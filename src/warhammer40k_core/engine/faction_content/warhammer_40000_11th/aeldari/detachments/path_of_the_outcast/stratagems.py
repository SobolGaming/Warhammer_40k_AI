from __future__ import annotations

from typing import cast

from warhammer40k_core.core.attributes import Characteristic
from warhammer40k_core.core.dice import DiceExpression, DiceRollSpec
from warhammer40k_core.core.modifiers import RollModifier
from warhammer40k_core.core.ruleset_descriptor import MovementMode
from warhammer40k_core.core.validation import IdentifierValidator
from warhammer40k_core.engine.army_mustering import ArmyDefinition
from warhammer40k_core.engine.battle_shock import (
    BattleShockResult,
    BattleShockTestReason,
    BattleShockTestRequest,
)
from warhammer40k_core.engine.battlefield_state import PlacementError
from warhammer40k_core.engine.decision import DiceRollManager
from warhammer40k_core.engine.effects import EffectExpiration, PersistingEffect
from warhammer40k_core.engine.event_log import JsonValue, validate_json_value
from warhammer40k_core.engine.faction_content.bundle import RuntimeContentContribution
from warhammer40k_core.engine.faction_content.common import (
    canonical_keyword as _canonical_keyword,
)
from warhammer40k_core.engine.faction_content.stratagem_handlers import (
    StratagemHandlerBinding,
    StratagemHandlerContext,
    StratagemHandlerExecutionResult,
)
from warhammer40k_core.engine.phase import BattlePhase, GameLifecycleError
from warhammer40k_core.engine.ranged_rule_effects import detection_range_bonus_payload
from warhammer40k_core.engine.reaction_windows import ReactionWindow, ReactionWindowKind
from warhammer40k_core.engine.stratagems import (
    HIT_ENEMY_UNIT_CONTEXT_KEY,
    HIT_ENEMY_UNIT_EFFECT_SELECTION_KIND,
    JUST_SHOT_UNIT_CONTEXT_KEY,
    JUST_SHOT_UNIT_TARGET_POLICY_ID,
    StratagemAvailabilityKind,
    StratagemCatalogRecord,
    StratagemCategory,
    StratagemDefinition,
    StratagemRestrictionPolicy,
    StratagemTargetKind,
    StratagemTargetSpec,
    StratagemTimingDescriptor,
    destroyed_target_unit_ids_from_context,
)
from warhammer40k_core.engine.timing_windows import TimingTriggerKind
from warhammer40k_core.engine.triggered_movement import (
    TriggeredMovementDescriptor,
    TriggeredMovementEligibleUnit,
    TriggeredMovementKind,
    triggered_movement_unit_selection_request,
)
from warhammer40k_core.engine.unit_factory import ModelInstance, UnitInstance
from warhammer40k_core.engine.unit_state import BelowHalfStrengthContext, StartingStrengthRecord

from .rule import (
    AELDARI_FACTION_ID,
    PATH_OF_THE_OUTCAST_DETACHMENT_ID,
    RANGERS,
    SHROUD_RUNNERS,
)

CONTRIBUTION_ID = "warhammer_40000_11th:aeldari:detachment:path_of_the_outcast:stratagems:scaffold"
SOURCE_RULE_ID = "phase17f:phase17e:aeldari:path-of-the-outcast:stratagems"
ELDRITCH_SUPPRESSION_STRATAGEM_ID = "aeldari:path-of-the-outcast:eldritch-suppression"
CASTING_BACK_THE_VEIL_STRATAGEM_ID = "aeldari:path-of-the-outcast:casting-back-the-veil"
NOMADS_OF_THE_HIDDEN_WAY_STRATAGEM_ID = "aeldari:path-of-the-outcast:nomads-of-the-hidden-way"
ELDRITCH_SUPPRESSION_HANDLER_ID = (
    "warhammer_40000_11th:aeldari:detachment:path_of_the_outcast:eldritch_suppression"
)
CASTING_BACK_THE_VEIL_HANDLER_ID = (
    "warhammer_40000_11th:aeldari:detachment:path_of_the_outcast:casting_back_the_veil"
)
NOMADS_OF_THE_HIDDEN_WAY_HANDLER_ID = (
    "warhammer_40000_11th:aeldari:detachment:path_of_the_outcast:nomads_of_the_hidden_way"
)
ELDRITCH_SUPPRESSION_RECORD_ID = f"{SOURCE_RULE_ID}:{ELDRITCH_SUPPRESSION_STRATAGEM_ID}"
CASTING_BACK_THE_VEIL_RECORD_ID = f"{SOURCE_RULE_ID}:{CASTING_BACK_THE_VEIL_STRATAGEM_ID}"
NOMADS_OF_THE_HIDDEN_WAY_RECORD_ID = f"{SOURCE_RULE_ID}:{NOMADS_OF_THE_HIDDEN_WAY_STRATAGEM_ID}"
CASTING_BACK_DETECTION_EFFECT_KIND = "aeldari_path_of_the_outcast_casting_back_the_veil"
NOMADS_RESTRICTION_EFFECT_KIND = "aeldari_path_of_the_outcast_nomads_restriction"


def runtime_contribution() -> RuntimeContentContribution:
    return RuntimeContentContribution(
        contribution_id=CONTRIBUTION_ID,
        stratagem_records=(
            _eldritch_suppression_record(),
            _casting_back_the_veil_record(),
            _nomads_of_the_hidden_way_record(),
        ),
        stratagem_handler_bindings=(
            StratagemHandlerBinding(
                handler_id=ELDRITCH_SUPPRESSION_HANDLER_ID,
                handler=apply_eldritch_suppression,
                validator=validate_eldritch_suppression,
            ),
            StratagemHandlerBinding(
                handler_id=CASTING_BACK_THE_VEIL_HANDLER_ID,
                handler=apply_casting_back_the_veil,
                validator=validate_casting_back_the_veil,
            ),
            StratagemHandlerBinding(
                handler_id=NOMADS_OF_THE_HIDDEN_WAY_HANDLER_ID,
                handler=apply_nomads_of_the_hidden_way,
                validator=validate_nomads_of_the_hidden_way,
            ),
        ),
    )


def apply_eldritch_suppression(
    context: StratagemHandlerContext,
) -> StratagemHandlerExecutionResult:
    validation = validate_eldritch_suppression(context)
    if validation.reason is not None:
        return validation
    enemy_unit_id = _hit_enemy_unit_id(context)
    enemy_owner = _unit_owner(context, unit_instance_id=enemy_unit_id)
    enemy_unit = _unit_by_id(context, unit_instance_id=enemy_unit_id)
    current_model_ids = _current_battlefield_model_ids(context, unit=enemy_unit)
    starting_strength = _starting_strength_record(context, unit_instance_id=enemy_unit_id)
    below_half_context = BelowHalfStrengthContext.from_unit(
        player_id=enemy_owner,
        unit=enemy_unit,
        starting_strength=starting_strength,
        current_model_ids=current_model_ids,
    )
    request = BattleShockTestRequest.for_unit(
        request_id=f"{context.use_record.use_id}:battle-shock:{enemy_unit_id}",
        game_id=context.state.game_id,
        battle_round=context.state.battle_round,
        player_id=enemy_owner,
        unit_instance_id=enemy_unit_id,
        reason=BattleShockTestReason.FORCED_BY_STRATAGEM,
        leadership_target=_best_leadership(enemy_unit, current_model_ids=current_model_ids),
        below_half_strength_context=below_half_context,
    )
    context.decisions.event_log.append(
        "battle_shock_test_requested",
        {
            "game_id": context.state.game_id,
            "battle_round": context.state.battle_round,
            "active_player_id": context.state.active_player_id,
            "phase": BattlePhase.SHOOTING.value,
            "battle_shock_test_request": validate_json_value(request.to_payload()),
            "source_stratagem_use": context.use_record.to_payload(),
        },
    )
    manager = DiceRollManager(context.state.game_id, event_log=context.decisions.event_log)
    roll_state = manager.roll(request.spec)
    modifiers = _eldritch_suppression_modifiers(context=context, enemy_unit_id=enemy_unit_id)
    result = BattleShockResult.from_roll_state(
        result_id=f"{request.request_id}:result",
        request=request,
        roll_state=roll_state,
        modifiers=modifiers,
    )
    context.state.record_battle_shock_result(result)
    context.decisions.event_log.append(
        "battle_shock_test_resolved",
        {
            "game_id": context.state.game_id,
            "battle_round": context.state.battle_round,
            "active_player_id": context.state.active_player_id,
            "phase": BattlePhase.SHOOTING.value,
            "battle_shock_result": validate_json_value(result.to_payload()),
            "auto_passed": False,
            "source_stratagem_use": context.use_record.to_payload(),
        },
    )
    replay_payload = {
        "effect_kind": "eldritch_suppression",
        "enemy_unit_instance_id": enemy_unit_id,
        "battle_shock_result_id": result.result_id,
        "destroyed_model_modifier_applied": bool(modifiers),
    }
    return StratagemHandlerExecutionResult.applied(
        handler_id=ELDRITCH_SUPPRESSION_HANDLER_ID,
        replay_payload=validate_json_value(replay_payload),
    )


def validate_eldritch_suppression(
    context: StratagemHandlerContext,
) -> StratagemHandlerExecutionResult:
    return _validate_path_stratagem(
        context,
        stratagem_id=ELDRITCH_SUPPRESSION_STRATAGEM_ID,
        handler_id=ELDRITCH_SUPPRESSION_HANDLER_ID,
        requires_hit_enemy=True,
    )


def apply_casting_back_the_veil(
    context: StratagemHandlerContext,
) -> StratagemHandlerExecutionResult:
    validation = validate_casting_back_the_veil(context)
    if validation.reason is not None:
        return validation
    enemy_unit_id = _hit_enemy_unit_id(context)
    effect = PersistingEffect(
        effect_id=f"{context.use_record.use_id}:casting-back-the-veil:{enemy_unit_id}",
        source_rule_id=SOURCE_RULE_ID,
        owner_player_id=context.use_record.player_id,
        target_unit_instance_ids=(enemy_unit_id,),
        started_battle_round=context.state.battle_round,
        started_phase=BattlePhase.SHOOTING,
        expiration=EffectExpiration.end_phase(
            battle_round=context.state.battle_round,
            phase=BattlePhase.SHOOTING,
            player_id=context.use_record.player_id,
        ),
        effect_payload=detection_range_bonus_payload(
            bonus_inches=6,
            source_rule_kind=CASTING_BACK_DETECTION_EFFECT_KIND,
            source_unit_instance_id=_shot_unit_id(context),
            source_decision_request_id=context.result.request_id,
            source_decision_result_id=context.result.result_id,
            stratagem_use_id=context.use_record.use_id,
        ),
    )
    context.state.record_persisting_effect(effect)
    context.decisions.event_log.append(
        "casting_back_the_veil_detection_range_granted",
        {
            "game_id": context.state.game_id,
            "battle_round": context.state.battle_round,
            "active_player_id": context.state.active_player_id,
            "phase": BattlePhase.SHOOTING.value,
            "stratagem_use": context.use_record.to_payload(),
            "persisting_effect": effect.to_payload(),
        },
    )
    return StratagemHandlerExecutionResult.applied(
        handler_id=CASTING_BACK_THE_VEIL_HANDLER_ID,
        replay_payload={
            "effect_kind": CASTING_BACK_DETECTION_EFFECT_KIND,
            "enemy_unit_instance_id": enemy_unit_id,
            "persisting_effect_id": effect.effect_id,
        },
    )


def validate_casting_back_the_veil(
    context: StratagemHandlerContext,
) -> StratagemHandlerExecutionResult:
    return _validate_path_stratagem(
        context,
        stratagem_id=CASTING_BACK_THE_VEIL_STRATAGEM_ID,
        handler_id=CASTING_BACK_THE_VEIL_HANDLER_ID,
        requires_hit_enemy=True,
    )


def apply_nomads_of_the_hidden_way(
    context: StratagemHandlerContext,
) -> StratagemHandlerExecutionResult:
    validation = validate_nomads_of_the_hidden_way(context)
    if validation.reason is not None:
        return validation
    unit_id = _target_unit_id(context)
    roll_state = DiceRollManager(context.state.game_id, event_log=context.decisions.event_log).roll(
        DiceRollSpec(
            expression=DiceExpression(quantity=1, sides=6),
            reason=f"Nomads of the Hidden Way move distance for {unit_id}",
            roll_type="nomads_of_the_hidden_way.distance",
            actor_id=context.use_record.player_id,
        )
    )
    distance_roll_payload = validate_json_value(roll_state.to_payload())
    restriction_effect = PersistingEffect(
        effect_id=f"{context.use_record.use_id}:nomads-restriction:{unit_id}",
        source_rule_id=SOURCE_RULE_ID,
        owner_player_id=context.use_record.player_id,
        target_unit_instance_ids=(unit_id,),
        started_battle_round=context.state.battle_round,
        started_phase=BattlePhase.SHOOTING,
        expiration=EffectExpiration.end_turn(
            battle_round=context.state.battle_round,
            player_id=context.use_record.player_id,
        ),
        effect_payload={
            "effect_kind": NOMADS_RESTRICTION_EFFECT_KIND,
            "charge_forbidden": True,
            "embark_transport_forbidden": True,
            "stratagem_use_id": context.use_record.use_id,
        },
    )
    context.state.record_persisting_effect(restriction_effect)
    trigger_event_id = _attack_sequence_completed_event_id(context)
    descriptor = TriggeredMovementDescriptor(
        movement_kind=TriggeredMovementKind.TRIGGERED,
        source_rule_id=SOURCE_RULE_ID,
        trigger_timing=ReactionWindow(
            phase=BattlePhase.SHOOTING,
            window_kind=ReactionWindowKind.RULE_TRIGGER,
            source_step="nomads_of_the_hidden_way",
            source_event_id=trigger_event_id,
        ),
        max_distance_inches=float(roll_state.current_total),
        movement_mode=MovementMode.NORMAL,
        allow_battle_shocked=False,
        allow_within_engagement_range=False,
        one_per_phase=False,
        optional=True,
    )
    request = triggered_movement_unit_selection_request(
        state=context.state,
        player_id=context.use_record.player_id,
        descriptor=descriptor,
        eligible_units=(
            TriggeredMovementEligibleUnit(
                unit_instance_id=unit_id,
                hook_id=NOMADS_OF_THE_HIDDEN_WAY_HANDLER_ID,
                source_id=SOURCE_RULE_ID,
                replay_payload={
                    "effect_kind": "nomads_of_the_hidden_way_move",
                    "stratagem_use_id": context.use_record.use_id,
                    "distance_roll": distance_roll_payload,
                },
                decision_effect_payload=None,
            ),
        ),
    )
    context.decisions.request_decision(request)
    context.decisions.event_log.append(
        "nomads_of_the_hidden_way_move_requested",
        {
            "game_id": context.state.game_id,
            "battle_round": context.state.battle_round,
            "active_player_id": context.state.active_player_id,
            "phase": BattlePhase.SHOOTING.value,
            "stratagem_use": context.use_record.to_payload(),
            "distance_roll": distance_roll_payload,
            "descriptor": descriptor.to_payload(),
            "restriction_effect": restriction_effect.to_payload(),
            "request_id": request.request_id,
            "phase_body_status": "nomads_of_the_hidden_way_move_pending",
        },
    )
    return StratagemHandlerExecutionResult.applied(
        handler_id=NOMADS_OF_THE_HIDDEN_WAY_HANDLER_ID,
        replay_payload={
            "effect_kind": "nomads_of_the_hidden_way",
            "unit_instance_id": unit_id,
            "distance_roll": distance_roll_payload,
            "restriction_effect_id": restriction_effect.effect_id,
            "triggered_movement_request_id": request.request_id,
        },
    )


def validate_nomads_of_the_hidden_way(
    context: StratagemHandlerContext,
) -> StratagemHandlerExecutionResult:
    return _validate_path_stratagem(
        context,
        stratagem_id=NOMADS_OF_THE_HIDDEN_WAY_STRATAGEM_ID,
        handler_id=NOMADS_OF_THE_HIDDEN_WAY_HANDLER_ID,
        requires_hit_enemy=False,
    )


def _eldritch_suppression_record() -> StratagemCatalogRecord:
    return _post_shot_record(
        record_id=ELDRITCH_SUPPRESSION_RECORD_ID,
        stratagem_id=ELDRITCH_SUPPRESSION_STRATAGEM_ID,
        name="Eldritch Suppression",
        category=StratagemCategory.BATTLE_TACTIC,
        effect_descriptor=(
            "Select one enemy unit hit by those ranged attacks. That enemy unit makes a "
            "Battle-shock roll, with -1 if a model in that enemy unit was destroyed by those "
            "attacks."
        ),
        handler_id=ELDRITCH_SUPPRESSION_HANDLER_ID,
        effect_payload={"effect_selection_kind": HIT_ENEMY_UNIT_EFFECT_SELECTION_KIND},
    )


def _casting_back_the_veil_record() -> StratagemCatalogRecord:
    return _post_shot_record(
        record_id=CASTING_BACK_THE_VEIL_RECORD_ID,
        stratagem_id=CASTING_BACK_THE_VEIL_STRATAGEM_ID,
        name="Casting Back the Veil",
        category=StratagemCategory.STRATEGIC_PLOY,
        effect_descriptor=(
            'Select one enemy unit hit by those ranged attacks. That enemy unit has +6" '
            "detection range."
        ),
        handler_id=CASTING_BACK_THE_VEIL_HANDLER_ID,
        effect_payload={"effect_selection_kind": HIT_ENEMY_UNIT_EFFECT_SELECTION_KIND},
    )


def _nomads_of_the_hidden_way_record() -> StratagemCatalogRecord:
    return _post_shot_record(
        record_id=NOMADS_OF_THE_HIDDEN_WAY_RECORD_ID,
        stratagem_id=NOMADS_OF_THE_HIDDEN_WAY_STRATAGEM_ID,
        name="Nomads of the Hidden Way",
        category=StratagemCategory.STRATEGIC_PLOY,
        effect_descriptor=(
            'Your unit can make a Normal move of up to D6". Until the end of the turn, '
            "your unit is not eligible to declare a charge or embark within a TRANSPORT."
        ),
        handler_id=NOMADS_OF_THE_HIDDEN_WAY_HANDLER_ID,
        effect_payload={"effect_kind": "nomads_of_the_hidden_way"},
    )


def _post_shot_record(
    *,
    record_id: str,
    stratagem_id: str,
    name: str,
    category: StratagemCategory,
    effect_descriptor: str,
    handler_id: str,
    effect_payload: JsonValue,
) -> StratagemCatalogRecord:
    return StratagemCatalogRecord(
        record_id=record_id,
        definition=StratagemDefinition(
            stratagem_id=stratagem_id,
            name=name,
            source_id=SOURCE_RULE_ID,
            command_point_cost=1,
            category=category,
            when_descriptor=(
                "Your Shooting phase, when a friendly RANGERS or SHROUD RUNNERS unit has shot."
            ),
            target_descriptor="That RANGERS or SHROUD RUNNERS unit.",
            effect_descriptor=effect_descriptor,
            restrictions_descriptor="Path of the Outcast Stratagem.",
            timing=StratagemTimingDescriptor(
                trigger_kind=TimingTriggerKind.JUST_AFTER_FRIENDLY_UNIT_HAS_SHOT,
                phase=BattlePhase.SHOOTING,
            ),
            restriction_policy=StratagemRestrictionPolicy(),
            target_spec=StratagemTargetSpec(
                target_kind=StratagemTargetKind.FRIENDLY_UNIT,
                enumerable=True,
                target_policy_id=JUST_SHOT_UNIT_TARGET_POLICY_ID,
                required_keywords_any=(RANGERS, SHROUD_RUNNERS),
            ),
            handler_id=handler_id,
            effect_payload=effect_payload,
        ),
        availability_kind=StratagemAvailabilityKind.DETACHMENT,
        detachment_id=PATH_OF_THE_OUTCAST_DETACHMENT_ID,
    )


def _validate_path_stratagem(
    context: StratagemHandlerContext,
    *,
    stratagem_id: str,
    handler_id: str,
    requires_hit_enemy: bool,
) -> StratagemHandlerExecutionResult:
    if type(context) is not StratagemHandlerContext:
        raise GameLifecycleError("Path of the Outcast requires a Stratagem handler context.")
    if context.definition.stratagem_id != stratagem_id:
        return StratagemHandlerExecutionResult.invalid(
            handler_id=handler_id,
            reason="wrong_stratagem",
        )
    if context.definition.handler_id != handler_id:
        return StratagemHandlerExecutionResult.invalid(
            handler_id=handler_id,
            reason="wrong_handler",
        )
    if context.eligibility_context.trigger_kind is not (
        TimingTriggerKind.JUST_AFTER_FRIENDLY_UNIT_HAS_SHOT
    ):
        return StratagemHandlerExecutionResult.invalid(handler_id=handler_id, reason="wrong_timing")
    if context.eligibility_context.phase is not BattlePhase.SHOOTING:
        return StratagemHandlerExecutionResult.invalid(handler_id=handler_id, reason="wrong_phase")
    if context.eligibility_context.active_player_id != context.use_record.player_id:
        return StratagemHandlerExecutionResult.invalid(
            handler_id=handler_id,
            reason="wrong_active_player",
        )
    target_unit_id = _target_unit_id(context)
    if target_unit_id != _shot_unit_id(context):
        return StratagemHandlerExecutionResult.invalid(
            handler_id=handler_id,
            reason="target_not_just_shot",
        )
    army = _army_for_player(context)
    if not _army_has_path_of_the_outcast(army):
        return StratagemHandlerExecutionResult.invalid(
            handler_id=handler_id,
            reason="detachment_missing",
        )
    unit = _unit_in_army(army=army, unit_instance_id=target_unit_id)
    if not (_unit_has_keyword(unit, RANGERS) or _unit_has_keyword(unit, SHROUD_RUNNERS)):
        return StratagemHandlerExecutionResult.invalid(
            handler_id=handler_id,
            reason="target_missing_rangers_or_shroud_runners",
        )
    if requires_hit_enemy:
        enemy_unit_id = _hit_enemy_unit_id(context)
        if _unit_owner(context, unit_instance_id=enemy_unit_id) == context.use_record.player_id:
            return StratagemHandlerExecutionResult.invalid(
                handler_id=handler_id,
                reason="hit_unit_not_enemy",
            )
        if (
            stratagem_id == ELDRITCH_SUPPRESSION_STRATAGEM_ID
            and enemy_unit_id in context.state.battle_shocked_unit_ids
        ):
            return StratagemHandlerExecutionResult.invalid(
                handler_id=handler_id,
                reason="target_already_battle_shocked",
            )
    return StratagemHandlerExecutionResult.applied(handler_id=handler_id)


def _eldritch_suppression_modifiers(
    *,
    context: StratagemHandlerContext,
    enemy_unit_id: str,
) -> tuple[RollModifier, ...]:
    if enemy_unit_id not in destroyed_target_unit_ids_from_context(context.eligibility_context):
        return ()
    return (
        RollModifier(
            modifier_id=f"{context.use_record.use_id}:eldritch-suppression:-1",
            source_id=SOURCE_RULE_ID,
            operand=-1,
        ),
    )


def _target_unit_id(context: StratagemHandlerContext) -> str:
    target_unit_id = context.target_binding.target_unit_instance_id
    if target_unit_id is None:
        raise GameLifecycleError("Path of the Outcast Stratagem requires a target unit.")
    return target_unit_id


def _shot_unit_id(context: StratagemHandlerContext) -> str:
    trigger_payload = context.eligibility_context.trigger_payload
    if not isinstance(trigger_payload, dict):
        raise GameLifecycleError("Path of the Outcast requires just-shot trigger context.")
    raw_unit_id = trigger_payload.get(JUST_SHOT_UNIT_CONTEXT_KEY)
    if type(raw_unit_id) is not str:
        raise GameLifecycleError("Path of the Outcast just-shot context is missing unit id.")
    return _validate_identifier("shot_unit_instance_id", raw_unit_id)


def _hit_enemy_unit_id(context: StratagemHandlerContext) -> str:
    effect_selection = context.use_record.effect_selection
    if not isinstance(effect_selection, dict):
        raise GameLifecycleError("Path of the Outcast requires hit enemy effect selection.")
    if effect_selection.get("effect_selection_kind") != HIT_ENEMY_UNIT_EFFECT_SELECTION_KIND:
        raise GameLifecycleError("Path of the Outcast effect selection kind drift.")
    raw_unit_id = effect_selection.get(HIT_ENEMY_UNIT_CONTEXT_KEY)
    if type(raw_unit_id) is not str:
        raise GameLifecycleError("Path of the Outcast effect selection is missing enemy unit.")
    return _validate_identifier("hit_enemy_unit_instance_id", raw_unit_id)


def _attack_sequence_completed_event_id(context: StratagemHandlerContext) -> str:
    trigger_payload = context.eligibility_context.trigger_payload
    if not isinstance(trigger_payload, dict):
        raise GameLifecycleError("Nomads of the Hidden Way requires shooting trigger context.")
    raw_event_id = trigger_payload.get("attack_sequence_completed_event_id")
    if type(raw_event_id) is not str:
        raise GameLifecycleError("Nomads of the Hidden Way trigger context is missing event id.")
    return _validate_identifier("attack_sequence_completed_event_id", raw_event_id)


def _army_for_player(context: StratagemHandlerContext) -> ArmyDefinition:
    for army in context.state.army_definitions:
        if army.player_id == context.use_record.player_id:
            return army
    raise GameLifecycleError("Path of the Outcast player army is unknown.")


def _army_has_path_of_the_outcast(army: ArmyDefinition) -> bool:
    return (
        army.detachment_selection.faction_id == AELDARI_FACTION_ID
        and PATH_OF_THE_OUTCAST_DETACHMENT_ID in army.detachment_selection.detachment_ids
    )


def _unit_in_army(*, army: ArmyDefinition, unit_instance_id: str) -> UnitInstance:
    requested_unit_id = _validate_identifier("unit_instance_id", unit_instance_id)
    for unit in army.units:
        if unit.unit_instance_id == requested_unit_id:
            return unit
    raise GameLifecycleError("Path of the Outcast target unit is not in the selected army.")


def _unit_by_id(context: StratagemHandlerContext, *, unit_instance_id: str) -> UnitInstance:
    requested_unit_id = _validate_identifier("unit_instance_id", unit_instance_id)
    for army in context.state.army_definitions:
        for unit in army.units:
            if unit.unit_instance_id == requested_unit_id:
                return unit
    raise GameLifecycleError("Path of the Outcast unit is unknown.")


def _unit_owner(context: StratagemHandlerContext, *, unit_instance_id: str) -> str:
    requested_unit_id = _validate_identifier("unit_instance_id", unit_instance_id)
    for army in context.state.army_definitions:
        if any(unit.unit_instance_id == requested_unit_id for unit in army.units):
            return army.player_id
    raise GameLifecycleError("Path of the Outcast unit owner is unknown.")


def _starting_strength_record(
    context: StratagemHandlerContext,
    *,
    unit_instance_id: str,
) -> StartingStrengthRecord:
    requested_unit_id = _validate_identifier("unit_instance_id", unit_instance_id)
    for record in context.state.starting_strength_records:
        if record.unit_instance_id == requested_unit_id:
            return record
    raise GameLifecycleError("Path of the Outcast target is missing starting strength.")


def _current_battlefield_model_ids(
    context: StratagemHandlerContext,
    *,
    unit: UnitInstance,
) -> tuple[str, ...]:
    battlefield_state = context.state.battlefield_state
    if battlefield_state is None:
        raise GameLifecycleError("Path of the Outcast requires battlefield state.")
    try:
        placement = battlefield_state.unit_placement_by_id(unit.unit_instance_id)
    except PlacementError as exc:
        raise GameLifecycleError("Path of the Outcast target unit is not placed.") from exc
    unit_model_by_id = {model.model_instance_id: model for model in unit.own_models}
    current_ids: list[str] = []
    for model_placement in placement.model_placements:
        model = unit_model_by_id.get(model_placement.model_instance_id)
        if model is None:
            raise GameLifecycleError("Battlefield placement contains unknown model.")
        if model.is_alive:
            current_ids.append(model.model_instance_id)
    if not current_ids:
        raise GameLifecycleError("Path of the Outcast target unit has no current models.")
    return tuple(sorted(current_ids))


def _best_leadership(unit: UnitInstance, *, current_model_ids: tuple[str, ...]) -> int:
    model_ids = set(_validate_identifier_tuple("current_model_ids", current_model_ids))
    leadership_values = tuple(
        _model_leadership(model)
        for model in unit.own_models
        if model.model_instance_id in model_ids
    )
    if not leadership_values:
        raise GameLifecycleError("Path of the Outcast found no current Leadership values.")
    return min(leadership_values)


def _model_leadership(model: ModelInstance) -> int:
    if type(model) is not ModelInstance:
        raise GameLifecycleError("Leadership lookup requires a ModelInstance.")
    for characteristic in model.characteristics:
        if characteristic.characteristic is Characteristic.LEADERSHIP:
            return characteristic.final
    raise GameLifecycleError("Path of the Outcast target model is missing Leadership.")


def _unit_has_keyword(unit: UnitInstance, keyword: str) -> bool:
    canonical = _canonical_keyword(keyword)
    return any(_canonical_keyword(stored) == canonical for stored in unit.keywords)


_validate_identifier = IdentifierValidator(GameLifecycleError)


def _validate_identifier_tuple(field_name: str, values: object) -> tuple[str, ...]:
    if type(values) is not tuple:
        raise GameLifecycleError(f"{field_name} must be a tuple.")
    identifiers: list[str] = []
    seen: set[str] = set()
    for value in cast(tuple[object, ...], values):
        identifier = _validate_identifier(f"{field_name} value", value)
        if identifier in seen:
            raise GameLifecycleError(f"{field_name} must not contain duplicates.")
        seen.add(identifier)
        identifiers.append(identifier)
    return tuple(sorted(identifiers))
