from __future__ import annotations

from dataclasses import dataclass
from typing import TYPE_CHECKING

from warhammer40k_core.core.datasheet import DatasheetAbilityDescriptor
from warhammer40k_core.core.ruleset_descriptor import BattlePhaseKind
from warhammer40k_core.core.validation import IdentifierValidator
from warhammer40k_core.engine.army_mustering import ArmyDefinition
from warhammer40k_core.engine.battlefield_state import (
    BattlefieldRuntimeState,
    BattlefieldScenario,
    ModelPlacement,
    geometry_model_for_placement,
)
from warhammer40k_core.engine.command_phase_start_hooks import (
    SELECT_FACTION_RULE_COMMAND_PHASE_START_OPTION_DECISION_TYPE,
    CommandPhaseStartRequestContext,
    CommandPhaseStartResultContext,
)
from warhammer40k_core.engine.decision_request import DecisionOption, DecisionRequest
from warhammer40k_core.engine.effects import EffectExpiration, PersistingEffect
from warhammer40k_core.engine.event_log import JsonValue, validate_json_value
from warhammer40k_core.engine.faction_rule_states import FactionRuleState
from warhammer40k_core.engine.phase import BattlePhase, GameLifecycleError, SetupStep
from warhammer40k_core.engine.unit_factory import ModelInstance, UnitInstance

if TYPE_CHECKING:
    from warhammer40k_core.engine.game_state import GameState

BONDSMAN_HOOK_ID = "warhammer_40000_11th:imperial_knights:army_rule:bondsman"
BONDSMAN_SOURCE_RULE_ID = "phase17g:imperial-knights:bondsman"
IMPERIAL_KNIGHTS_FACTION_ID = "imperial-knights"
IMPERIAL_KNIGHTS_FACTION_KEYWORD = "IMPERIAL KNIGHTS"
ARMIGER_KEYWORD = "ARMIGER"
BONDSMAN_ABILITY_NAME = "Bondsman"
BONDSMAN_RANGE_INCHES = 12.0
BONDSMAN_SELECTION_KIND = "imperial_knights_bondsman_application"
BONDSMAN_EFFECT_KIND = "imperial_knights_bondsman"
BONDSMAN_APPLIED_STATE_KIND = "imperial_knights_bondsman_applied"
BONDSMAN_DONE_STATE_KIND = "imperial_knights_bondsman_command_phase_done"
BONDSMAN_APPLIED_EVENT = "imperial_knights_bondsman_applied"
BONDSMAN_DONE_EVENT = "imperial_knights_bondsman_done"
BONDSMAN_DONE_OPTION_ID = "imperial_knights:bondsman:done"


@dataclass(frozen=True, slots=True)
class BondsmanApplicationOption:
    source_unit: UnitInstance
    source_model: ModelInstance
    target_unit: UnitInstance
    target_model: ModelInstance
    ability: DatasheetAbilityDescriptor

    def __post_init__(self) -> None:
        if type(self.source_unit) is not UnitInstance:
            raise GameLifecycleError("Bondsman option requires source unit.")
        if type(self.source_model) is not ModelInstance:
            raise GameLifecycleError("Bondsman option requires source model.")
        if type(self.target_unit) is not UnitInstance:
            raise GameLifecycleError("Bondsman option requires target unit.")
        if type(self.target_model) is not ModelInstance:
            raise GameLifecycleError("Bondsman option requires target model.")
        if type(self.ability) is not DatasheetAbilityDescriptor:
            raise GameLifecycleError("Bondsman option requires ability descriptor.")


def bondsman_request(
    context: CommandPhaseStartRequestContext,
) -> DecisionRequest | None:
    if type(context) is not CommandPhaseStartRequestContext:
        raise GameLifecycleError("Bondsman requires request context.")
    army = _imperial_knights_army_for_player(
        context.state,
        player_id=context.active_player_id,
    )
    if army is None:
        return None
    if _bondsman_done_this_command_phase(context.state, player_id=army.player_id):
        return None

    applications = _eligible_bondsman_applications(context.state, army=army)
    if not applications:
        return None

    common_payload = _bondsman_payload_object(
        validate_json_value(
            {
                "game_id": context.state.game_id,
                "battle_round": context.state.battle_round,
                "phase": BattlePhase.COMMAND.value,
                "active_player_id": army.player_id,
                "player_id": army.player_id,
                "faction_id": IMPERIAL_KNIGHTS_FACTION_ID,
                "source_rule_id": BONDSMAN_SOURCE_RULE_ID,
                "hook_id": BONDSMAN_HOOK_ID,
                "effect_kind": BONDSMAN_EFFECT_KIND,
                "selection_kind": BONDSMAN_SELECTION_KIND,
                "range_inches": BONDSMAN_RANGE_INCHES,
                "eligible_application_option_ids": [
                    _bondsman_application_option_id(application) for application in applications
                ],
                "expires_at_battle_round": _next_own_turn_battle_round(context.state),
            }
        )
    )
    return DecisionRequest(
        request_id=context.state.next_decision_request_id(),
        decision_type=SELECT_FACTION_RULE_COMMAND_PHASE_START_OPTION_DECISION_TYPE,
        actor_id=army.player_id,
        payload=validate_json_value(common_payload),
        options=(
            *tuple(
                _bondsman_application_decision_option(application, common_payload)
                for application in applications
            ),
            DecisionOption(
                option_id=BONDSMAN_DONE_OPTION_ID,
                label="No more Bondsman abilities",
                payload=validate_json_value(
                    {
                        **common_payload,
                        "submission_kind": BONDSMAN_SELECTION_KIND,
                        "selected_bondsman_option": "done",
                    }
                ),
            ),
        ),
    )


def apply_bondsman_result(context: CommandPhaseStartResultContext) -> bool:
    if type(context) is not CommandPhaseStartResultContext:
        raise GameLifecycleError("Bondsman requires result context.")
    if (
        context.request.decision_type
        != SELECT_FACTION_RULE_COMMAND_PHASE_START_OPTION_DECISION_TYPE
    ):
        return False
    request_payload = _bondsman_payload_object(context.request.payload)
    if request_payload.get("hook_id") != BONDSMAN_HOOK_ID:
        return False
    context.result.validate_for_request(context.request)
    if context.result.actor_id is None:
        raise GameLifecycleError("Bondsman result requires an actor.")

    player_id = context.result.actor_id
    army = _imperial_knights_army_for_player(context.state, player_id=player_id)
    if army is None:
        raise GameLifecycleError("Bondsman actor does not own Imperial Knights.")
    if _bondsman_done_this_command_phase(context.state, player_id=player_id):
        raise GameLifecycleError("Bondsman was already completed this Command phase.")

    payload = _bondsman_payload_object(context.result.payload)
    _validate_bondsman_common_payload_context(
        context=context,
        request_payload=request_payload,
        payload=payload,
    )
    selected = _bondsman_payload_string(payload, key="selected_bondsman_option")
    if selected == "done":
        if context.result.selected_option_id != BONDSMAN_DONE_OPTION_ID:
            raise GameLifecycleError("Bondsman done option ID drift.")
        _record_bondsman_done(context, player_id=player_id)
        return True
    if selected != "apply":
        raise GameLifecycleError("Bondsman selection is unsupported.")

    current_applications = {
        _bondsman_application_option_id(application): application
        for application in _eligible_bondsman_applications(context.state, army=army)
    }
    application = current_applications.get(context.result.selected_option_id)
    if application is None:
        raise GameLifecycleError("Bondsman selection is no longer eligible.")
    _validate_bondsman_application_payload(payload=payload, application=application)
    _record_bondsman_application(context, player_id=player_id, application=application)
    return True


def active_bondsman_ability_id_for_model(
    state: GameState,
    *,
    model_instance_id: str,
) -> str | None:
    effect = _active_bondsman_effect_for_model(state, model_instance_id=model_instance_id)
    if effect is None:
        return None
    payload = _bondsman_payload_object(effect.effect_payload)
    return _bondsman_payload_string(payload, key="bondsman_ability_id")


def model_is_affected_by_bondsman(
    state: GameState,
    *,
    model_instance_id: str,
) -> bool:
    return (
        active_bondsman_ability_id_for_model(
            state,
            model_instance_id=model_instance_id,
        )
        is not None
    )


def _record_bondsman_application(
    context: CommandPhaseStartResultContext,
    *,
    player_id: str,
    application: BondsmanApplicationOption,
) -> None:
    application_state = _bondsman_application_state(
        context=context,
        player_id=player_id,
        application=application,
    )
    effect = _bondsman_effect(
        context=context,
        player_id=player_id,
        application=application,
        application_state=application_state,
    )
    context.state.record_faction_rule_state(application_state)
    context.state.record_persisting_effect(effect)
    context.decisions.event_log.append(
        BONDSMAN_APPLIED_EVENT,
        {
            "game_id": context.state.game_id,
            "battle_round": context.state.battle_round,
            "phase": BattlePhase.COMMAND.value,
            "player_id": player_id,
            "source_bondsman_unit_instance_id": application.source_unit.unit_instance_id,
            "source_bondsman_model_instance_id": application.source_model.model_instance_id,
            "target_armiger_unit_instance_id": application.target_unit.unit_instance_id,
            "target_armiger_model_instance_id": application.target_model.model_instance_id,
            "bondsman_ability_id": application.ability.ability_id,
            "bondsman_ability_name": application.ability.name,
            "faction_rule_state": validate_json_value(application_state.to_payload()),
            "persisting_effect": validate_json_value(effect.to_payload()),
            "source_rule_id": BONDSMAN_SOURCE_RULE_ID,
            "hook_id": BONDSMAN_HOOK_ID,
            "request_id": context.request.request_id,
            "result_id": context.result.result_id,
        },
    )


def _record_bondsman_done(
    context: CommandPhaseStartResultContext,
    *,
    player_id: str,
) -> None:
    done_state = FactionRuleState(
        state_id=(
            f"imperial-knights:bondsman:done:{context.state.game_id}:"
            f"round-{context.state.battle_round:02d}:{player_id}:command"
        ),
        player_id=player_id,
        faction_id=IMPERIAL_KNIGHTS_FACTION_ID,
        source_rule_id=BONDSMAN_SOURCE_RULE_ID,
        state_kind=BONDSMAN_DONE_STATE_KIND,
        setup_step=SetupStep.DECLARE_BATTLE_FORMATIONS,
        request_id=context.request.request_id,
        result_id=context.result.result_id,
        payload=validate_json_value(
            {
                "game_id": context.state.game_id,
                "battle_round": context.state.battle_round,
                "phase": BattlePhase.COMMAND.value,
                "active_player_id": context.active_player_id,
                "player_id": player_id,
                "selected_bondsman_option": "done",
                "source_rule_id": BONDSMAN_SOURCE_RULE_ID,
                "hook_id": BONDSMAN_HOOK_ID,
            }
        ),
    )
    context.state.record_faction_rule_state(done_state)
    context.decisions.event_log.append(
        BONDSMAN_DONE_EVENT,
        {
            "game_id": context.state.game_id,
            "battle_round": context.state.battle_round,
            "phase": BattlePhase.COMMAND.value,
            "player_id": player_id,
            "faction_rule_state": validate_json_value(done_state.to_payload()),
            "source_rule_id": BONDSMAN_SOURCE_RULE_ID,
            "hook_id": BONDSMAN_HOOK_ID,
            "request_id": context.request.request_id,
            "result_id": context.result.result_id,
        },
    )


def _bondsman_application_decision_option(
    application: BondsmanApplicationOption,
    common_payload: dict[str, JsonValue],
) -> DecisionOption:
    option_id = _bondsman_application_option_id(application)
    return DecisionOption(
        option_id=option_id,
        label=(
            f"Use {application.ability.name}: "
            f"{application.source_model.name} to {application.target_model.name}"
        ),
        payload=validate_json_value(
            {
                **common_payload,
                "submission_kind": BONDSMAN_SELECTION_KIND,
                "selected_bondsman_option": "apply",
                "selected_option_id": option_id,
                "source_bondsman_unit_instance_id": application.source_unit.unit_instance_id,
                "source_bondsman_unit_name": application.source_unit.name,
                "source_bondsman_model_instance_id": application.source_model.model_instance_id,
                "source_bondsman_model_name": application.source_model.name,
                "target_armiger_unit_instance_id": application.target_unit.unit_instance_id,
                "target_armiger_unit_name": application.target_unit.name,
                "target_armiger_model_instance_id": application.target_model.model_instance_id,
                "target_armiger_model_name": application.target_model.name,
                "rules_unit_instance_id": application.target_unit.unit_instance_id,
                "rules_unit_owner_player_id": common_payload["player_id"],
                "bondsman_ability_id": application.ability.ability_id,
                "bondsman_ability_name": application.ability.name,
                "bondsman_ability_source_id": application.ability.source_id,
            }
        ),
    )


def _eligible_bondsman_applications(
    state: GameState,
    *,
    army: ArmyDefinition,
) -> tuple[BondsmanApplicationOption, ...]:
    _validate_game_state(state)
    if type(army) is not ArmyDefinition:
        raise GameLifecycleError("Bondsman application lookup requires ArmyDefinition.")
    applications: list[BondsmanApplicationOption] = []
    for source_unit in army.units:
        if not _unit_has_faction_keyword(source_unit, IMPERIAL_KNIGHTS_FACTION_KEYWORD):
            continue
        source_abilities = _bondsman_abilities_for_unit(source_unit)
        if not source_abilities:
            continue
        for source_model in source_unit.alive_own_models():
            if not _model_is_on_battlefield(
                state,
                model_instance_id=source_model.model_instance_id,
            ):
                continue
            for ability in source_abilities:
                if _source_model_used_bondsman_this_command_phase(
                    state,
                    player_id=army.player_id,
                    source_model_instance_id=source_model.model_instance_id,
                    bondsman_ability_id=ability.ability_id,
                ):
                    continue
                for target_unit, target_model in _eligible_bondsman_targets(
                    state,
                    army=army,
                    source_model=source_model,
                ):
                    applications.append(
                        BondsmanApplicationOption(
                            source_unit=source_unit,
                            source_model=source_model,
                            target_unit=target_unit,
                            target_model=target_model,
                            ability=ability,
                        )
                    )
    return tuple(sorted(applications, key=_bondsman_application_option_id))


def _eligible_bondsman_targets(
    state: GameState,
    *,
    army: ArmyDefinition,
    source_model: ModelInstance,
) -> tuple[tuple[UnitInstance, ModelInstance], ...]:
    targets: list[tuple[UnitInstance, ModelInstance]] = []
    for target_unit in army.units:
        if not _unit_has_keyword(target_unit, ARMIGER_KEYWORD):
            continue
        for target_model in target_unit.alive_own_models():
            target_model_id = target_model.model_instance_id
            if target_model_id == source_model.model_instance_id:
                continue
            if _active_bondsman_effect_for_model(state, model_instance_id=target_model_id):
                continue
            if not _model_is_on_battlefield(state, model_instance_id=target_model_id):
                continue
            if not _models_within_bondsman_range(
                state=state,
                source_model_instance_id=source_model.model_instance_id,
                target_model_instance_id=target_model_id,
            ):
                continue
            targets.append((target_unit, target_model))
    return tuple(
        sorted(
            targets,
            key=lambda item: (item[0].unit_instance_id, item[1].model_instance_id),
        )
    )


def _bondsman_application_state(
    *,
    context: CommandPhaseStartResultContext,
    player_id: str,
    application: BondsmanApplicationOption,
) -> FactionRuleState:
    return FactionRuleState(
        state_id=(
            f"imperial-knights:bondsman:applied:{context.state.game_id}:"
            f"round-{context.state.battle_round:02d}:{player_id}:"
            f"{application.source_model.model_instance_id}:"
            f"{application.ability.ability_id}:"
            f"{application.target_model.model_instance_id}:"
            f"{context.result.result_id}"
        ),
        player_id=player_id,
        faction_id=IMPERIAL_KNIGHTS_FACTION_ID,
        source_rule_id=BONDSMAN_SOURCE_RULE_ID,
        state_kind=BONDSMAN_APPLIED_STATE_KIND,
        setup_step=SetupStep.DECLARE_BATTLE_FORMATIONS,
        request_id=context.request.request_id,
        result_id=context.result.result_id,
        payload=validate_json_value(
            {
                "game_id": context.state.game_id,
                "battle_round": context.state.battle_round,
                "phase": BattlePhase.COMMAND.value,
                "active_player_id": context.active_player_id,
                "player_id": player_id,
                "faction_id": IMPERIAL_KNIGHTS_FACTION_ID,
                "source_bondsman_unit_instance_id": application.source_unit.unit_instance_id,
                "source_bondsman_model_instance_id": application.source_model.model_instance_id,
                "target_armiger_unit_instance_id": application.target_unit.unit_instance_id,
                "target_armiger_model_instance_id": application.target_model.model_instance_id,
                "bondsman_ability_id": application.ability.ability_id,
                "bondsman_ability_name": application.ability.name,
                "bondsman_ability_source_id": application.ability.source_id,
                "source_rule_id": BONDSMAN_SOURCE_RULE_ID,
                "hook_id": BONDSMAN_HOOK_ID,
                "selected_option_id": context.result.selected_option_id,
            }
        ),
    )


def _bondsman_effect(
    *,
    context: CommandPhaseStartResultContext,
    player_id: str,
    application: BondsmanApplicationOption,
    application_state: FactionRuleState,
) -> PersistingEffect:
    expiration_battle_round = _next_own_turn_battle_round(context.state)
    expiration = EffectExpiration.start_turn(
        battle_round=expiration_battle_round,
        player_id=player_id,
    )
    return PersistingEffect(
        effect_id=(
            f"imperial-knights:bondsman:effect:{context.state.game_id}:"
            f"round-{context.state.battle_round:02d}:{player_id}:"
            f"{application.target_model.model_instance_id}:{context.result.result_id}"
        ),
        source_rule_id=BONDSMAN_SOURCE_RULE_ID,
        owner_player_id=player_id,
        target_unit_instance_ids=(application.target_unit.unit_instance_id,),
        started_battle_round=context.state.battle_round,
        started_phase=BattlePhaseKind.COMMAND,
        expiration=expiration,
        effect_payload=validate_json_value(
            {
                "game_id": context.state.game_id,
                "battle_round": context.state.battle_round,
                "phase": BattlePhase.COMMAND.value,
                "active_player_id": context.active_player_id,
                "player_id": player_id,
                "faction_id": IMPERIAL_KNIGHTS_FACTION_ID,
                "effect_kind": BONDSMAN_EFFECT_KIND,
                "source_bondsman_unit_instance_id": application.source_unit.unit_instance_id,
                "source_bondsman_model_instance_id": application.source_model.model_instance_id,
                "target_armiger_unit_instance_id": application.target_unit.unit_instance_id,
                "target_armiger_model_instance_id": application.target_model.model_instance_id,
                "target_unit_instance_ids": [application.target_unit.unit_instance_id],
                "bondsman_ability_id": application.ability.ability_id,
                "bondsman_ability_name": application.ability.name,
                "bondsman_ability_source_id": application.ability.source_id,
                "source_rule_id": BONDSMAN_SOURCE_RULE_ID,
                "hook_id": BONDSMAN_HOOK_ID,
                "request_id": context.request.request_id,
                "result_id": context.result.result_id,
                "faction_rule_state_id": application_state.state_id,
                "selected_option_id": context.result.selected_option_id,
                "expires_at_battle_round": expiration_battle_round,
            }
        ),
    )


def _bondsman_abilities_for_unit(
    unit: UnitInstance,
) -> tuple[DatasheetAbilityDescriptor, ...]:
    if type(unit) is not UnitInstance:
        raise GameLifecycleError("Bondsman ability lookup requires UnitInstance.")
    return tuple(
        sorted(
            (ability for ability in unit.datasheet_abilities if _ability_has_bondsman_tag(ability)),
            key=lambda ability: ability.ability_id,
        )
    )


def _ability_has_bondsman_tag(ability: DatasheetAbilityDescriptor) -> bool:
    if type(ability) is not DatasheetAbilityDescriptor:
        raise GameLifecycleError("Bondsman tag lookup requires ability descriptor.")
    bondsman_token = _normalise_rule_token(BONDSMAN_ABILITY_NAME)
    descriptor_tokens = {
        _normalise_rule_token(token) for token in (*ability.timing_tags, *ability.parameter_tokens)
    }
    if bondsman_token in descriptor_tokens:
        return True
    name_token = _normalise_rule_token(ability.name)
    return name_token == bondsman_token or name_token.endswith(bondsman_token)


def _source_model_used_bondsman_this_command_phase(
    state: GameState,
    *,
    player_id: str,
    source_model_instance_id: str,
    bondsman_ability_id: str,
) -> bool:
    requested_player_id = _validate_identifier("player_id", player_id)
    requested_source_model_id = _validate_identifier(
        "source_model_instance_id",
        source_model_instance_id,
    )
    requested_ability_id = _validate_identifier("bondsman_ability_id", bondsman_ability_id)
    matching = tuple(
        stored
        for stored in state.faction_rule_states_for_player(
            player_id=requested_player_id,
            state_kind=BONDSMAN_APPLIED_STATE_KIND,
        )
        if _bondsman_application_state_matches_current_command_phase(
            state,
            stored,
            source_model_instance_id=requested_source_model_id,
            bondsman_ability_id=requested_ability_id,
        )
    )
    if len(matching) > 1:
        raise GameLifecycleError("Bondsman found duplicate source model applications.")
    return bool(matching)


def _bondsman_application_state_matches_current_command_phase(
    state: GameState,
    stored: FactionRuleState,
    *,
    source_model_instance_id: str,
    bondsman_ability_id: str,
) -> bool:
    payload = _bondsman_payload_object(stored.payload)
    return (
        stored.source_rule_id == BONDSMAN_SOURCE_RULE_ID
        and payload.get("battle_round") == state.battle_round
        and payload.get("phase") == BattlePhase.COMMAND.value
        and payload.get("source_bondsman_model_instance_id") == source_model_instance_id
        and payload.get("bondsman_ability_id") == bondsman_ability_id
    )


def _bondsman_done_this_command_phase(state: GameState, *, player_id: str) -> bool:
    requested_player_id = _validate_identifier("player_id", player_id)
    matching = tuple(
        stored
        for stored in state.faction_rule_states_for_player(
            player_id=requested_player_id,
            state_kind=BONDSMAN_DONE_STATE_KIND,
        )
        if _bondsman_done_state_matches_current_command_phase(state, stored)
    )
    if len(matching) > 1:
        raise GameLifecycleError("Bondsman found multiple done states.")
    return bool(matching)


def _bondsman_done_state_matches_current_command_phase(
    state: GameState,
    stored: FactionRuleState,
) -> bool:
    payload = _bondsman_payload_object(stored.payload)
    return (
        stored.source_rule_id == BONDSMAN_SOURCE_RULE_ID
        and payload.get("battle_round") == state.battle_round
        and payload.get("phase") == BattlePhase.COMMAND.value
        and payload.get("selected_bondsman_option") == "done"
    )


def _active_bondsman_effect_for_model(
    state: GameState,
    *,
    model_instance_id: str,
) -> PersistingEffect | None:
    _validate_game_state(state)
    target_model_id = _validate_identifier("model_instance_id", model_instance_id)
    target_unit = _unit_for_model_id(state, model_instance_id=target_model_id)
    effects: list[PersistingEffect] = []
    for effect in state.persisting_effects_for_unit(target_unit.unit_instance_id):
        if effect.source_rule_id != BONDSMAN_SOURCE_RULE_ID:
            continue
        payload = _bondsman_payload_object(effect.effect_payload)
        if payload.get("effect_kind") != BONDSMAN_EFFECT_KIND:
            continue
        if payload.get("target_armiger_model_instance_id") != target_model_id:
            continue
        effects.append(effect)
    if len(effects) > 1:
        raise GameLifecycleError("Bondsman found multiple active effects for model.")
    return effects[0] if effects else None


def _models_within_bondsman_range(
    *,
    state: GameState,
    source_model_instance_id: str,
    target_model_instance_id: str,
) -> bool:
    battlefield = _battlefield_state(state)
    source_placement = _model_placement_or_none(
        state,
        model_instance_id=source_model_instance_id,
    )
    target_placement = _model_placement_or_none(
        state,
        model_instance_id=target_model_instance_id,
    )
    if source_placement is None or target_placement is None:
        return False
    scenario = BattlefieldScenario(
        armies=tuple(state.army_definitions),
        battlefield_state=battlefield,
    )
    source_model = geometry_model_for_placement(
        model=scenario.model_instance_for_placement(source_placement),
        placement=source_placement,
    )
    target_model = geometry_model_for_placement(
        model=scenario.model_instance_for_placement(target_placement),
        placement=target_placement,
    )
    return source_model.range_to(target_model) <= BONDSMAN_RANGE_INCHES


def _model_is_on_battlefield(state: GameState, *, model_instance_id: str) -> bool:
    return _model_placement_or_none(state, model_instance_id=model_instance_id) is not None


def _model_placement_or_none(
    state: GameState,
    *,
    model_instance_id: str,
) -> ModelPlacement | None:
    battlefield = _battlefield_state(state)
    requested_model_id = _validate_identifier("model_instance_id", model_instance_id)
    for placed_army in battlefield.placed_armies:
        for unit_placement in placed_army.unit_placements:
            for model_placement in unit_placement.model_placements:
                if model_placement.model_instance_id == requested_model_id:
                    return model_placement
    return None


def _unit_for_model_id(state: GameState, *, model_instance_id: str) -> UnitInstance:
    requested_model_id = _validate_identifier("model_instance_id", model_instance_id)
    for army in state.army_definitions:
        for unit in army.units:
            if any(model.model_instance_id == requested_model_id for model in unit.own_models):
                return unit
    raise GameLifecycleError("Bondsman model_instance_id was not found.")


def _bondsman_application_option_id(application: BondsmanApplicationOption) -> str:
    return (
        "imperial_knights:bondsman:"
        f"{application.source_model.model_instance_id}:"
        f"{application.ability.ability_id}:"
        f"{application.target_model.model_instance_id}"
    )


def _validate_bondsman_common_payload_context(
    *,
    context: CommandPhaseStartResultContext,
    request_payload: dict[str, JsonValue],
    payload: dict[str, JsonValue],
) -> None:
    if request_payload.get("game_id") != context.state.game_id:
        raise GameLifecycleError("Bondsman request game drift.")
    if request_payload.get("battle_round") != context.state.battle_round:
        raise GameLifecycleError("Bondsman request battle round drift.")
    if request_payload.get("phase") != BattlePhase.COMMAND.value:
        raise GameLifecycleError("Bondsman request phase drift.")
    if _bondsman_payload_string(payload, key="submission_kind") != BONDSMAN_SELECTION_KIND:
        raise GameLifecycleError("Bondsman payload submission_kind drift.")
    if _bondsman_payload_string(payload, key="player_id") != context.result.actor_id:
        raise GameLifecycleError("Bondsman payload player drift.")
    if _bondsman_payload_string(payload, key="hook_id") != BONDSMAN_HOOK_ID:
        raise GameLifecycleError("Bondsman payload hook drift.")
    if _bondsman_payload_string(payload, key="source_rule_id") != BONDSMAN_SOURCE_RULE_ID:
        raise GameLifecycleError("Bondsman payload source rule drift.")


def _validate_bondsman_application_payload(
    *,
    payload: dict[str, JsonValue],
    application: BondsmanApplicationOption,
) -> None:
    if _bondsman_payload_string(payload, key="selected_option_id") != (
        _bondsman_application_option_id(application)
    ):
        raise GameLifecycleError("Bondsman selected option payload drift.")
    if _bondsman_payload_string(payload, key="source_bondsman_unit_instance_id") != (
        application.source_unit.unit_instance_id
    ):
        raise GameLifecycleError("Bondsman source unit payload drift.")
    if _bondsman_payload_string(payload, key="source_bondsman_model_instance_id") != (
        application.source_model.model_instance_id
    ):
        raise GameLifecycleError("Bondsman source model payload drift.")
    if _bondsman_payload_string(payload, key="target_armiger_unit_instance_id") != (
        application.target_unit.unit_instance_id
    ):
        raise GameLifecycleError("Bondsman target unit payload drift.")
    if _bondsman_payload_string(payload, key="target_armiger_model_instance_id") != (
        application.target_model.model_instance_id
    ):
        raise GameLifecycleError("Bondsman target model payload drift.")
    if _bondsman_payload_string(payload, key="bondsman_ability_id") != (
        application.ability.ability_id
    ):
        raise GameLifecycleError("Bondsman ability payload drift.")


def _battlefield_state(state: GameState) -> BattlefieldRuntimeState:
    if state.battlefield_state is None:
        raise GameLifecycleError("Bondsman requires battlefield_state.")
    return state.battlefield_state


def _next_own_turn_battle_round(state: GameState) -> int:
    _validate_game_state(state)
    return state.battle_round + 1


def _bondsman_payload_object(payload: JsonValue) -> dict[str, JsonValue]:
    if not isinstance(payload, dict):
        raise GameLifecycleError("Bondsman payload must be an object.")
    return payload


def _bondsman_payload_string(payload: dict[str, JsonValue], *, key: str) -> str:
    value = payload.get(key)
    if type(value) is not str or not value.strip():
        raise GameLifecycleError(f"Bondsman payload {key} must be a string.")
    return value


def _imperial_knights_armies(state: GameState) -> tuple[ArmyDefinition, ...]:
    _validate_game_state(state)
    return tuple(
        army
        for army in state.army_definitions
        if army.detachment_selection.faction_id == IMPERIAL_KNIGHTS_FACTION_ID
    )


def _imperial_knights_army_for_player(
    state: GameState,
    *,
    player_id: str,
) -> ArmyDefinition | None:
    requested_player_id = _validate_identifier("player_id", player_id)
    matches = tuple(
        army for army in _imperial_knights_armies(state) if army.player_id == requested_player_id
    )
    if len(matches) > 1:
        raise GameLifecycleError("Player has multiple Imperial Knights armies.")
    return matches[0] if matches else None


def _unit_has_keyword(unit: UnitInstance, keyword: str) -> bool:
    if type(unit) is not UnitInstance:
        raise GameLifecycleError("Bondsman unit keyword check requires UnitInstance.")
    requested_keyword = _canonical_keyword(keyword)
    return requested_keyword in {_canonical_keyword(item) for item in unit.keywords}


def _unit_has_faction_keyword(unit: UnitInstance, keyword: str) -> bool:
    if type(unit) is not UnitInstance:
        raise GameLifecycleError("Bondsman faction keyword check requires UnitInstance.")
    requested_keyword = _canonical_keyword(keyword)
    return requested_keyword in {_canonical_keyword(item) for item in unit.faction_keywords}


def _validate_game_state(state: object) -> GameState:
    from warhammer40k_core.engine.game_state import GameState

    if type(state) is not GameState:
        raise GameLifecycleError("Bondsman requires GameState.")
    return state


_validate_identifier = IdentifierValidator(GameLifecycleError)


def _canonical_keyword(value: str) -> str:
    return _validate_identifier("keyword", value).upper().replace("_", " ")


def _normalise_rule_token(value: str) -> str:
    return "".join(character for character in value.upper() if character.isalnum())
