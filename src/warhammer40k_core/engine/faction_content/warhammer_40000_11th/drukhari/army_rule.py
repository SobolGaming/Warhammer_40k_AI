from __future__ import annotations

from warhammer40k_core.core.ruleset_descriptor import BattlePhaseKind
from warhammer40k_core.core.validation import IdentifierValidator
from warhammer40k_core.engine.advance_hooks import (
    AdvanceMoveContext,
    AdvanceMoveGrant,
    AdvanceMoveHookBinding,
)
from warhammer40k_core.engine.army_mustering import ArmyDefinition
from warhammer40k_core.engine.battle_shock_hooks import (
    BattleShockHookBinding,
    BattleShockOutcomeContext,
)
from warhammer40k_core.engine.charge_declaration_hooks import (
    ChargeDeclarationContext,
    ChargeDeclarationGrant,
    ChargeDeclarationHookBinding,
)
from warhammer40k_core.engine.command_phase_start_hooks import (
    CommandPhaseStartContext,
    CommandPhaseStartHookBinding,
)
from warhammer40k_core.engine.event_log import EventRecord, validate_json_value
from warhammer40k_core.engine.faction_content.bundle import RuntimeContentContribution
from warhammer40k_core.engine.faction_content.warhammer_40000_11th.drukhari.power_from_pain import (
    DRUKHARI_FACTION_ID,
    HATRED_ETERNAL_ABILITY_KEY,
    LITHE_AGILITY_ABILITY_KEY,
    PAIN_TOKEN_RESOURCE_KIND,
    SOURCE_RULE_ID,
    drukhari_rules_unit_can_empower_for_ability,
    hatred_eternal_hit_reroll_permission,
    lithe_agility_advance_reroll_permission,
    lithe_agility_charge_reroll_permission,
    pain_token_spend_effect_payload,
    pain_tokens_available,
    power_from_pain_reroll_permission_effect_payload,
    power_from_pain_target_unit_ids,
)
from warhammer40k_core.engine.faction_resources import FactionResourceStatus
from warhammer40k_core.engine.fight_unit_selected_hooks import (
    FightUnitSelectedContext,
    FightUnitSelectedGrant,
    FightUnitSelectedGrantBinding,
)
from warhammer40k_core.engine.phase import BattlePhase, GameLifecycleError
from warhammer40k_core.engine.shooting_unit_selected_hooks import (
    ShootingUnitSelectedContext,
    ShootingUnitSelectedGrant,
    ShootingUnitSelectedGrantBinding,
)
from warhammer40k_core.engine.unit_destroyed_hooks import (
    UnitDestroyedContext,
    UnitDestroyedHookBinding,
)

CONTRIBUTION_ID = "warhammer_40000_11th:drukhari:army_rule:scaffold"
HOOK_ID = "warhammer_40000_11th:drukhari:army_rule:power_from_pain"
LITHE_AGILITY_ADVANCE_HOOK_ID = f"{HOOK_ID}:lithe-agility-advance"
LITHE_AGILITY_CHARGE_HOOK_ID = f"{HOOK_ID}:lithe-agility-charge"
HATRED_ETERNAL_SHOOTING_HOOK_ID = f"{HOOK_ID}:hatred-eternal-shooting"
HATRED_ETERNAL_FIGHT_HOOK_ID = f"{HOOK_ID}:hatred-eternal-fight"


def runtime_contribution() -> RuntimeContentContribution:
    return RuntimeContentContribution(
        contribution_id=CONTRIBUTION_ID,
        advance_move_hook_bindings=(
            AdvanceMoveHookBinding(
                hook_id=LITHE_AGILITY_ADVANCE_HOOK_ID,
                source_id=SOURCE_RULE_ID,
                handler=lithe_agility_advance_grant,
            ),
        ),
        charge_declaration_hook_bindings=(
            ChargeDeclarationHookBinding(
                hook_id=LITHE_AGILITY_CHARGE_HOOK_ID,
                source_id=SOURCE_RULE_ID,
                handler=lithe_agility_charge_declaration_grant,
            ),
        ),
        shooting_unit_selected_grant_hook_bindings=(
            ShootingUnitSelectedGrantBinding(
                hook_id=HATRED_ETERNAL_SHOOTING_HOOK_ID,
                source_id=SOURCE_RULE_ID,
                handler=hatred_eternal_shooting_unit_selected_grant,
            ),
        ),
        fight_unit_selected_grant_hook_bindings=(
            FightUnitSelectedGrantBinding(
                hook_id=HATRED_ETERNAL_FIGHT_HOOK_ID,
                source_id=SOURCE_RULE_ID,
                handler=hatred_eternal_fight_unit_selected_grant,
            ),
        ),
        command_phase_start_hook_bindings=(
            CommandPhaseStartHookBinding(
                hook_id=f"{HOOK_ID}:command-phase-start",
                source_id=SOURCE_RULE_ID,
                handler=resolve_command_phase_start,
            ),
        ),
        battle_shock_hook_bindings=(
            BattleShockHookBinding(
                hook_id=f"{HOOK_ID}:battle-shock-failed",
                source_id=SOURCE_RULE_ID,
                outcome_handler=resolve_battle_shock_outcome,
            ),
        ),
        unit_destroyed_hook_bindings=(
            UnitDestroyedHookBinding(
                hook_id=f"{HOOK_ID}:enemy-unit-destroyed",
                source_id=SOURCE_RULE_ID,
                handler=resolve_enemy_unit_destroyed,
            ),
        ),
    )


def hatred_eternal_shooting_unit_selected_grant(
    context: ShootingUnitSelectedContext,
) -> ShootingUnitSelectedGrant | None:
    if type(context) is not ShootingUnitSelectedContext:
        raise GameLifecycleError("Power from Pain Hatred Eternal requires selected unit context.")
    if not _hatred_eternal_empowerment_available(
        state=context.state,
        player_id=context.player_id,
        unit_instance_id=context.unit_instance_id,
    ):
        return None
    return ShootingUnitSelectedGrant(
        hook_id=HATRED_ETERNAL_SHOOTING_HOOK_ID,
        source_id=SOURCE_RULE_ID,
        label="Power from Pain: Hatred Eternal",
        replay_payload={
            "trigger": "selected_to_shoot",
            "unit_instance_id": context.unit_instance_id,
            "selection_request_id": context.request_id,
            "selection_result_id": context.result_id,
        },
        decision_effect_payload=pain_token_spend_effect_payload(),
        unit_effect_payload=power_from_pain_reroll_permission_effect_payload(
            unit_instance_id=context.unit_instance_id,
            target_unit_instance_ids=power_from_pain_target_unit_ids(
                context.state,
                unit_instance_id=context.unit_instance_id,
            ),
            trigger="selected_to_shoot",
            phase=BattlePhaseKind.SHOOTING,
            pain_ability_keys=(HATRED_ETERNAL_ABILITY_KEY,),
            permission=hatred_eternal_hit_reroll_permission(
                state=context.state,
                player_id=context.player_id,
                unit_instance_id=context.unit_instance_id,
            ),
            source_context={
                "selection_request_id": context.request_id,
                "selection_result_id": context.result_id,
            },
        ),
        unit_effect_expiration="end_phase",
    )


def hatred_eternal_fight_unit_selected_grant(
    context: FightUnitSelectedContext,
) -> FightUnitSelectedGrant | None:
    if type(context) is not FightUnitSelectedContext:
        raise GameLifecycleError("Power from Pain Hatred Eternal requires selected fight context.")
    if not _hatred_eternal_empowerment_available(
        state=context.state,
        player_id=context.player_id,
        unit_instance_id=context.unit_instance_id,
    ):
        return None
    return FightUnitSelectedGrant(
        hook_id=HATRED_ETERNAL_FIGHT_HOOK_ID,
        source_id=SOURCE_RULE_ID,
        label="Power from Pain: Hatred Eternal",
        replay_payload={
            "trigger": "selected_to_fight",
            "unit_instance_id": context.unit_instance_id,
            "activation_request_id": context.request_id,
            "activation_result_id": context.result_id,
            "fight_type": context.fight_type,
            "ordering_band": context.ordering_band,
        },
        decision_effect_payload=pain_token_spend_effect_payload(),
        unit_effect_payload=power_from_pain_reroll_permission_effect_payload(
            unit_instance_id=context.unit_instance_id,
            target_unit_instance_ids=power_from_pain_target_unit_ids(
                context.state,
                unit_instance_id=context.unit_instance_id,
            ),
            trigger="selected_to_fight",
            phase=BattlePhaseKind.FIGHT,
            pain_ability_keys=(HATRED_ETERNAL_ABILITY_KEY,),
            permission=hatred_eternal_hit_reroll_permission(
                state=context.state,
                player_id=context.player_id,
                unit_instance_id=context.unit_instance_id,
            ),
            source_context={
                "activation_request_id": context.request_id,
                "activation_result_id": context.result_id,
                "fight_type": context.fight_type,
                "ordering_band": context.ordering_band,
            },
        ),
        unit_effect_expiration="end_phase",
    )


def lithe_agility_advance_grant(context: AdvanceMoveContext) -> AdvanceMoveGrant | None:
    if type(context) is not AdvanceMoveContext:
        raise GameLifecycleError("Power from Pain Lithe Agility requires AdvanceMoveContext.")
    if context.movement_phase_action != "advance":
        return None
    if not _lithe_agility_empowerment_available(
        state=context.state,
        player_id=context.player_id,
        unit_instance_id=context.unit_instance_id,
    ):
        return None
    return AdvanceMoveGrant(
        hook_id=LITHE_AGILITY_ADVANCE_HOOK_ID,
        source_id=SOURCE_RULE_ID,
        label="Power from Pain: Lithe Agility",
        granted_ranged_weapon_keywords=(),
        replay_payload={
            "trigger": "advance",
            "unit_instance_id": context.unit_instance_id,
            "movement_action_request_id": context.movement_request_id,
            "movement_action_result_id": context.movement_result_id,
        },
        decision_effect_payload=pain_token_spend_effect_payload(),
        unit_effect_payload=power_from_pain_reroll_permission_effect_payload(
            unit_instance_id=context.unit_instance_id,
            target_unit_instance_ids=power_from_pain_target_unit_ids(
                context.state,
                unit_instance_id=context.unit_instance_id,
            ),
            trigger="advance",
            phase=BattlePhaseKind.MOVEMENT,
            pain_ability_keys=(LITHE_AGILITY_ABILITY_KEY,),
            permission=lithe_agility_advance_reroll_permission(
                state=context.state,
                player_id=context.player_id,
                unit_instance_id=context.unit_instance_id,
            ),
            source_context={
                "movement_action_request_id": context.movement_request_id,
                "movement_action_result_id": context.movement_result_id,
            },
        ),
        unit_effect_expiration="end_phase",
    )


def lithe_agility_charge_declaration_grant(
    context: ChargeDeclarationContext,
) -> ChargeDeclarationGrant | None:
    if type(context) is not ChargeDeclarationContext:
        raise GameLifecycleError("Power from Pain Lithe Agility requires ChargeDeclarationContext.")
    if not _lithe_agility_empowerment_available(
        state=context.state,
        player_id=context.player_id,
        unit_instance_id=context.unit_instance_id,
    ):
        return None
    return ChargeDeclarationGrant(
        hook_id=LITHE_AGILITY_CHARGE_HOOK_ID,
        source_id=SOURCE_RULE_ID,
        label="Power from Pain: Lithe Agility",
        replay_payload={
            "trigger": "charge",
            "unit_instance_id": context.unit_instance_id,
            "selection_request_id": context.selection_request_id,
            "selection_result_id": context.selection_result_id,
        },
        decision_effect_payload=pain_token_spend_effect_payload(),
        unit_effect_payload=power_from_pain_reroll_permission_effect_payload(
            unit_instance_id=context.unit_instance_id,
            target_unit_instance_ids=power_from_pain_target_unit_ids(
                context.state,
                unit_instance_id=context.unit_instance_id,
            ),
            trigger="charge",
            phase=BattlePhaseKind.CHARGE,
            pain_ability_keys=(LITHE_AGILITY_ABILITY_KEY,),
            permission=lithe_agility_charge_reroll_permission(
                state=context.state,
                player_id=context.player_id,
                unit_instance_id=context.unit_instance_id,
            ),
            source_context={
                "selection_request_id": context.selection_request_id,
                "selection_result_id": context.selection_result_id,
            },
        ),
        unit_effect_expiration="end_phase",
    )


def _lithe_agility_empowerment_available(
    *,
    state: object,
    player_id: str,
    unit_instance_id: str,
) -> bool:
    if pain_tokens_available(state, player_id=player_id) <= 0:
        return False
    return drukhari_rules_unit_can_empower_for_ability(
        state,
        player_id=player_id,
        unit_instance_id=unit_instance_id,
        pain_ability_key=LITHE_AGILITY_ABILITY_KEY,
    )


def _hatred_eternal_empowerment_available(
    *,
    state: object,
    player_id: str,
    unit_instance_id: str,
) -> bool:
    if pain_tokens_available(state, player_id=player_id) <= 0:
        return False
    return drukhari_rules_unit_can_empower_for_ability(
        state,
        player_id=player_id,
        unit_instance_id=unit_instance_id,
        pain_ability_key=HATRED_ETERNAL_ABILITY_KEY,
    )


def resolve_command_phase_start(context: CommandPhaseStartContext) -> None:
    if type(context) is not CommandPhaseStartContext:
        raise GameLifecycleError("Power from Pain command hook requires context.")
    active_player_id = context.active_player_id
    army = _drukhari_army_for_player(context.state.army_definitions, player_id=active_player_id)
    if army is None:
        return
    gain = context.state.gain_faction_resource(
        player_id=active_player_id,
        resource_kind=PAIN_TOKEN_RESOURCE_KIND,
        amount=1,
        source_id=(
            f"{SOURCE_RULE_ID}:command-phase-start:"
            f"round-{context.state.battle_round:02d}:player-{active_player_id}"
        ),
    )
    if gain.status is not FactionResourceStatus.APPLIED:
        raise GameLifecycleError("Power from Pain command token gain failed.")
    context.decisions.event_log.append(
        "drukhari_pain_token_gained",
        {
            "game_id": context.state.game_id,
            "battle_round": context.state.battle_round,
            "phase": BattlePhase.COMMAND.value,
            "player_id": active_player_id,
            "source_rule_id": SOURCE_RULE_ID,
            "hook_id": f"{HOOK_ID}:command-phase-start",
            "trigger": "command_phase_start",
            "faction_resource_result": validate_json_value(gain.to_payload()),
        },
    )


def resolve_battle_shock_outcome(context: BattleShockOutcomeContext) -> None:
    if type(context) is not BattleShockOutcomeContext:
        raise GameLifecycleError("Power from Pain Battle-shock hook requires context.")
    if context.result.passed:
        return
    target_player_id = context.result.request.player_id
    for army in _drukhari_armies(context.state.army_definitions):
        if army.player_id == target_player_id:
            continue
        source_id = (
            f"{SOURCE_RULE_ID}:enemy-battle-shock-failed:"
            f"{context.result.result_id}:player-{army.player_id}"
        )
        if _pain_token_gain_event_exists(context.decisions.event_log.records, source_id=source_id):
            continue
        gain = context.state.gain_faction_resource(
            player_id=army.player_id,
            resource_kind=PAIN_TOKEN_RESOURCE_KIND,
            amount=1,
            source_id=source_id,
        )
        if gain.status is not FactionResourceStatus.APPLIED:
            raise GameLifecycleError("Power from Pain Battle-shock token gain failed.")
        context.decisions.event_log.append(
            "drukhari_pain_token_gained",
            {
                "game_id": context.state.game_id,
                "battle_round": context.state.battle_round,
                "phase": context.phase.value,
                "player_id": army.player_id,
                "source_rule_id": SOURCE_RULE_ID,
                "hook_id": f"{HOOK_ID}:battle-shock-failed",
                "trigger": "enemy_battle_shock_failed",
                "enemy_player_id": target_player_id,
                "enemy_unit_instance_id": context.result.request.unit_instance_id,
                "battle_shock_result_id": context.result.result_id,
                "faction_resource_result": validate_json_value(gain.to_payload()),
            },
        )


def resolve_enemy_unit_destroyed(context: UnitDestroyedContext) -> None:
    if type(context) is not UnitDestroyedContext:
        raise GameLifecycleError("Power from Pain unit-destroyed hook requires context.")
    army = _drukhari_army_for_player(
        context.state.army_definitions,
        player_id=context.destroying_player_id,
    )
    if army is None:
        return
    source_id = (
        f"{SOURCE_RULE_ID}:enemy-unit-destroyed:"
        f"{context.model_destroyed_event_id}:player-{army.player_id}"
    )
    if _pain_token_gain_event_exists(context.decisions.event_log.records, source_id=source_id):
        return
    gain = context.state.gain_faction_resource(
        player_id=army.player_id,
        resource_kind=PAIN_TOKEN_RESOURCE_KIND,
        amount=1,
        source_id=source_id,
    )
    if gain.status is not FactionResourceStatus.APPLIED:
        raise GameLifecycleError("Power from Pain enemy-unit-destroyed token gain failed.")
    context.decisions.event_log.append(
        "drukhari_pain_token_gained",
        {
            "game_id": context.state.game_id,
            "battle_round": context.state.battle_round,
            "phase": context.completed_phase.value,
            "player_id": army.player_id,
            "source_rule_id": SOURCE_RULE_ID,
            "hook_id": f"{HOOK_ID}:enemy-unit-destroyed",
            "trigger": "enemy_unit_destroyed",
            "enemy_player_id": context.destroyed_player_id,
            "enemy_unit_instance_id": context.destroyed_unit_instance_id,
            "model_destroyed_event_id": context.model_destroyed_event_id,
            "faction_resource_result": validate_json_value(gain.to_payload()),
        },
    )


def _drukhari_armies(armies: list[ArmyDefinition]) -> tuple[ArmyDefinition, ...]:
    return tuple(
        army for army in armies if army.detachment_selection.faction_id == DRUKHARI_FACTION_ID
    )


def _drukhari_army_for_player(
    armies: list[ArmyDefinition],
    *,
    player_id: str,
) -> ArmyDefinition | None:
    requested_player_id = _validate_identifier("player_id", player_id)
    for army in _drukhari_armies(armies):
        if army.player_id == requested_player_id:
            return army
    return None


def _pain_token_gain_event_exists(records: tuple[EventRecord, ...], *, source_id: str) -> bool:
    requested_source_id = _validate_identifier("source_id", source_id)
    for record in records:
        if type(record) is not EventRecord:
            raise GameLifecycleError("Power from Pain records must be EventRecord values.")
        if record.event_type != "drukhari_pain_token_gained":
            continue
        payload = record.payload
        if not isinstance(payload, dict):
            raise GameLifecycleError("Power from Pain event payload must be an object.")
        resource_payload = payload.get("faction_resource_result")
        if not isinstance(resource_payload, dict):
            raise GameLifecycleError("Power from Pain resource payload is malformed.")
        if resource_payload.get("source_id") == requested_source_id:
            return True
    return False


_validate_identifier = IdentifierValidator(GameLifecycleError)
