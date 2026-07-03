from __future__ import annotations

from collections.abc import Callable
from dataclasses import replace
from pathlib import Path
from typing import cast

import pytest
from tests.unit.test_phase11c_command_phase import (
    _battle_state,  # pyright: ignore[reportPrivateUsage]
)
from tests.unit.test_phase13b_shooting_declarations import (
    _catalog_with_replaced_bolt_profiles,  # pyright: ignore[reportPrivateUsage]
    _proposal_from_request,  # pyright: ignore[reportPrivateUsage]
    _shooting_lifecycle,  # pyright: ignore[reportPrivateUsage]
    _weapon_profile_by_wargear,  # pyright: ignore[reportPrivateUsage]
)
from tests.unit.test_phase15c_fight_order import (
    _advance_to_fight_order_request,  # pyright: ignore[reportPrivateUsage]
    _fight_lifecycle,  # pyright: ignore[reportPrivateUsage]
    _submit_minimal_melee_declaration,  # pyright: ignore[reportPrivateUsage]
)

from warhammer40k_core.core.army_catalog import ArmyCatalog
from warhammer40k_core.core.attributes import Characteristic, CharacteristicValue
from warhammer40k_core.core.datasheet import (
    CatalogAbilitySourceKind,
    CatalogAbilitySupport,
    DatasheetAbilityDescriptor,
)
from warhammer40k_core.core.dice import (
    DiceExpression,
    DiceRollSpec,
    DiceRollState,
    DiceRollStatePayload,
    RerollComponentSelectionPolicy,
    RerollPermission,
)
from warhammer40k_core.core.ruleset_descriptor import BattlePhaseKind, RulesetDescriptor
from warhammer40k_core.core.weapon_profiles import AttackProfile
from warhammer40k_core.engine.abilities import AbilityCatalogIndex
from warhammer40k_core.engine.advance_hooks import (
    SELECT_ADVANCE_MOVE_GRANT_DECISION_TYPE,
    AdvanceMoveContext,
)
from warhammer40k_core.engine.army_mustering import ArmyDefinition
from warhammer40k_core.engine.attack_sequence import (
    AttackSequence,
    AttackSequenceStep,
    _request_source_backed_hit_reroll_if_available,
    _source_backed_reroll_already_answered,
    attack_sequence_hit_roll_spec,
    attack_sequence_wound_roll_spec,
)
from warhammer40k_core.engine.battle_shock import (
    BATTLE_SHOCK_ROLL_TYPE,
    BattleShockResult,
    BattleShockTestReason,
    BattleShockTestRequest,
)
from warhammer40k_core.engine.battle_shock_hooks import BattleShockOutcomeContext
from warhammer40k_core.engine.charge_declaration_hooks import (
    SELECT_CHARGE_DECLARATION_GRANT_DECISION_TYPE,
    ChargeDeclarationContext,
)
from warhammer40k_core.engine.command_phase_start_hooks import (
    CommandPhaseStartContext,
    CommandPhaseStartHandler,
    CommandPhaseStartHookBinding,
    CommandPhaseStartHookRegistry,
)
from warhammer40k_core.engine.decision_controller import DecisionController
from warhammer40k_core.engine.decision_request import DecisionOption, DecisionRequest
from warhammer40k_core.engine.decision_result import DecisionResult
from warhammer40k_core.engine.dice import DICE_REROLL_DECISION_TYPE, DiceRollManager
from warhammer40k_core.engine.effects import EffectExpiration, PersistingEffect
from warhammer40k_core.engine.event_log import JsonValue, validate_json_value
from warhammer40k_core.engine.faction_content.warhammer_40000_11th.drukhari import (
    army_rule,
)
from warhammer40k_core.engine.faction_content.warhammer_40000_11th.drukhari.power_from_pain import (
    HATRED_ETERNAL_ABILITY_KEY,
    LITHE_AGILITY_ABILITY_KEY,
    PAIN_TOKEN_RESOURCE_KIND,
    SOURCE_RULE_ID,
    drukhari_rules_unit_can_empower_for_ability,
    lithe_agility_advance_reroll_permission,
    lithe_agility_charge_reroll_permission,
    pain_ability_keys_for_rules_unit,
    pain_tokens_available,
    power_from_pain_empowerment_payload,
    power_from_pain_reroll_permission_effect_payload,
    power_from_pain_target_unit_ids,
    spend_pain_token,
    unit_is_empowered_through_pain_for_ability,
)
from warhammer40k_core.engine.faction_resources import (
    FACTION_RESOURCE_SPEND_EFFECT_KIND,
    FactionResourceLedger,
    FactionResourceResult,
    FactionResourceStatus,
    FactionResourceTransaction,
    FactionResourceTransactionKind,
    apply_faction_resource_spend_effect,
    faction_resource_result_enriched_payload,
    faction_resource_spend_effect_payload,
    faction_resource_status_from_token,
    faction_resource_transaction_kind_from_token,
    initial_faction_resource_ledgers,
)
from warhammer40k_core.engine.fight_order import fight_activation_option_id
from warhammer40k_core.engine.fight_resolution import (
    SUBMIT_MELEE_DECLARATION_DECISION_TYPE,
    MeleeDeclarationProposalRequest,
)
from warhammer40k_core.engine.fight_unit_selected_hooks import (
    SELECT_FIGHT_UNIT_GRANT_DECISION_TYPE,
    FightUnitSelectedContext,
    FightUnitSelectedGrant,
    FightUnitSelectedGrantBinding,
    FightUnitSelectedGrantRegistry,
)
from warhammer40k_core.engine.game_state import GameState
from warhammer40k_core.engine.lifecycle import GameLifecycle
from warhammer40k_core.engine.phase import (
    BattlePhase,
    GameLifecycleError,
    LifecycleStatus,
    LifecycleStatusKind,
)
from warhammer40k_core.engine.phases.charge import (
    ChargingUnitSelection,
    _charge_reroll_permission_for_unit,  # pyright: ignore[reportPrivateUsage]
    _record_charge_declaration_grant_effects,  # pyright: ignore[reportPrivateUsage]
)
from warhammer40k_core.engine.phases.command import CommandPhaseHandler
from warhammer40k_core.engine.phases.movement import (
    _advance_reroll_permission_for_unit,
    _record_movement_action_grant_effects,
)
from warhammer40k_core.engine.phases.shooting import (
    SELECT_SHOOTING_TYPE_DECISION_TYPE,
    SELECT_SHOOTING_UNIT_DECISION_TYPE,
    SUBMIT_SHOOTING_DECLARATION_DECISION_TYPE,
    ShootingPhaseHandler,
    ShootingPhaseState,
    ShootingUnitSelection,
    _record_shooting_unit_selected_grant_effects,  # pyright: ignore[reportPrivateUsage]
    _request_shooting_unit_selected_grant_decision_if_available,  # pyright: ignore[reportPrivateUsage]
)
from warhammer40k_core.engine.shooting_types import ShootingType
from warhammer40k_core.engine.shooting_unit_selected_hooks import (
    DECLINE_SHOOTING_UNIT_GRANT_OPTION_ID,
    SELECT_SHOOTING_UNIT_GRANT_DECISION_TYPE,
    ShootingUnitSelectedContext,
    ShootingUnitSelectedGrant,
    ShootingUnitSelectedGrantBinding,
    ShootingUnitSelectedGrantRegistry,
)
from warhammer40k_core.engine.source_backed_rerolls import (
    SOURCE_BACKED_REROLL_PERMISSION_EFFECT_KIND,
    source_backed_reroll_permission_effect_payload,
    source_backed_reroll_permission_for_unit,
    source_payload_from_reroll_effect_payload,
)
from warhammer40k_core.engine.stratagems import StratagemCatalogIndex
from warhammer40k_core.engine.unit_destroyed_hooks import (
    UnitDestroyedContext,
    UnitDestroyedHandler,
    UnitDestroyedHookBinding,
    UnitDestroyedHookRegistry,
)
from warhammer40k_core.engine.unit_factory import UnitInstance
from warhammer40k_core.engine.unit_state import BelowHalfStrengthContext
from warhammer40k_core.engine.weapon_declaration import RangedAttackPool
from warhammer40k_core.geometry.pose import Pose


def test_power_from_pain_command_start_gains_pain_token() -> None:
    state = _battle_state()
    _mark_player_as_drukhari(state, player_id="player-a")
    decisions = DecisionController()
    handler = CommandPhaseHandler(
        stratagem_index=StratagemCatalogIndex.from_records(()),
        command_phase_start_hooks=CommandPhaseStartHookRegistry.from_bindings(
            army_rule.runtime_contribution().command_phase_start_hook_bindings
        ),
    )

    completed = handler.begin_phase(state=state, decisions=decisions)

    assert completed.status_kind is LifecycleStatusKind.ADVANCED
    assert pain_tokens_available(state, player_id="player-a") == 1
    payload = _last_event_payload(decisions, "drukhari_pain_token_gained")
    assert payload["trigger"] == "command_phase_start"
    assert payload["player_id"] == "player-a"


def test_power_from_pain_failed_enemy_battle_shock_gains_pain_token() -> None:
    state = _battle_state()
    _mark_player_as_drukhari(state, player_id="player-a")
    target_unit = _unit_for_player(state, player_id="player-b")
    decisions = DecisionController()
    manager = DiceRollManager(state.game_id, event_log=decisions.event_log)
    request = BattleShockTestRequest(
        request_id="drukhari-test-battle-shock",
        game_id=state.game_id,
        battle_round=state.battle_round,
        player_id="player-b",
        unit_instance_id=target_unit.unit_instance_id,
        reason=BattleShockTestReason.BELOW_HALF_STRENGTH,
        leadership_target=7,
        below_half_strength_context=BelowHalfStrengthContext(
            player_id="player-b",
            unit_instance_id=target_unit.unit_instance_id,
            starting_model_count=5,
            current_model_count=2,
            single_model_starting_wounds=None,
            single_model_wounds_remaining=None,
        ),
        spec=DiceRollSpec(
            expression=DiceExpression(quantity=2, sides=6),
            reason=f"Battle-shock test for {target_unit.unit_instance_id}",
            roll_type=BATTLE_SHOCK_ROLL_TYPE,
            actor_id=target_unit.unit_instance_id,
        ),
    )
    roll_state = manager.roll_fixed(request.spec, [1, 1])
    result = BattleShockResult.from_roll_state(
        result_id="drukhari-test-battle-shock:result",
        request=request,
        roll_state=roll_state,
    )

    army_rule.resolve_battle_shock_outcome(
        BattleShockOutcomeContext(
            state=state,
            decisions=decisions,
            dice_manager=manager,
            result=result,
            active_player_id="player-b",
            phase=BattlePhase.COMMAND,
            auto_passed=False,
            phase_start_battle_shocked_unit_ids=(),
        )
    )

    assert pain_tokens_available(state, player_id="player-a") == 1
    payload = _last_event_payload(decisions, "drukhari_pain_token_gained")
    assert payload["trigger"] == "enemy_battle_shock_failed"
    assert payload["enemy_player_id"] == "player-b"
    assert payload["enemy_unit_instance_id"] == target_unit.unit_instance_id


def test_power_from_pain_enemy_unit_destroyed_gains_one_pain_token() -> None:
    state = _battle_state()
    _mark_player_as_drukhari(state, player_id="player-a")
    target_unit = _unit_for_player(state, player_id="player-b")
    decisions = DecisionController()
    destroyed_event = decisions.event_log.append(
        "model_destroyed",
        {
            "game_id": state.game_id,
            "battle_round": state.battle_round,
            "active_player_id": state.active_player_id,
            "phase": BattlePhase.SHOOTING.value,
            "destroying_player_id": "player-a",
            "target_unit_instance_id": target_unit.unit_instance_id,
            "model_instance_id": target_unit.own_models[-1].model_instance_id,
        },
    )

    army_rule.resolve_enemy_unit_destroyed(
        UnitDestroyedContext(
            state=state,
            decisions=decisions,
            completed_phase=BattlePhase.SHOOTING,
            model_destroyed_event_id=destroyed_event.event_id,
            model_destroyed_payload=cast(dict[str, JsonValue], destroyed_event.payload),
            destroying_player_id="player-a",
            destroyed_unit_instance_id=target_unit.unit_instance_id,
            destroyed_player_id="player-b",
        )
    )

    assert pain_tokens_available(state, player_id="player-a") == 1
    payload = _last_event_payload(decisions, "drukhari_pain_token_gained")
    assert payload["trigger"] == "enemy_unit_destroyed"
    assert payload["model_destroyed_event_id"] == destroyed_event.event_id


def test_pain_token_ledger_payload_round_trips_after_spend() -> None:
    state = _battle_state()
    _mark_player_as_drukhari(state, player_id="player-a")
    state.gain_faction_resource(
        player_id="player-a",
        resource_kind=PAIN_TOKEN_RESOURCE_KIND,
        amount=2,
        source_id="drukhari-test:gain",
    )

    spend_payload = spend_pain_token(
        state,
        player_id="player-a",
        source_id="drukhari-test:spend",
    )
    restored = GameState.from_payload(state.to_payload())

    assert pain_tokens_available(state, player_id="player-a") == 1
    assert pain_tokens_available(restored, player_id="player-a") == 1
    assert cast(dict[str, JsonValue], spend_payload)["status"] == "applied"


def test_lithe_agility_advance_grant_spends_pain_token_and_empowers_unit() -> None:
    state = _battle_state()
    _set_current_battle_phase(state, BattlePhase.MOVEMENT)
    _mark_player_as_drukhari(
        state,
        player_id="player-a",
        datasheet_abilities=(_lithe_agility_ability(),),
    )
    unit = _unit_for_player(state, player_id="player-a")
    state.gain_faction_resource(
        player_id="player-a",
        resource_kind=PAIN_TOKEN_RESOURCE_KIND,
        amount=1,
        source_id="drukhari-test:lithe-advance-token",
    )

    grant = army_rule.lithe_agility_advance_grant(
        AdvanceMoveContext(
            state=state,
            player_id="player-a",
            battle_round=state.battle_round,
            unit_instance_id=unit.unit_instance_id,
            movement_phase_action="advance",
            movement_request_id="drukhari-test:advance-request",
            movement_result_id="drukhari-test:advance-result",
        )
    )

    assert grant is not None
    effects = _record_movement_action_grant_effects(
        state=state,
        player_id="player-a",
        unit_instance_id=unit.unit_instance_id,
        result=DecisionResult(
            result_id="drukhari-test:lithe-advance-grant-result",
            request_id="drukhari-test:lithe-advance-grant-request",
            decision_type=SELECT_ADVANCE_MOVE_GRANT_DECISION_TYPE,
            actor_id="player-a",
            selected_option_id=grant.hook_id,
            payload=validate_json_value(grant.to_payload()),
        ),
        grant=grant,
    )

    assert pain_tokens_available(state, player_id="player-a") == 0
    assert len(effects) == 2
    assert unit_is_empowered_through_pain_for_ability(
        state=state,
        player_id="player-a",
        unit_instance_id=unit.unit_instance_id,
        pain_ability_key=LITHE_AGILITY_ABILITY_KEY,
    )


def test_lithe_agility_charge_grant_spends_pain_token_and_unlocks_charge_reroll() -> None:
    state = _battle_state()
    _set_current_battle_phase(state, BattlePhase.CHARGE)
    _mark_player_as_drukhari(
        state,
        player_id="player-a",
        datasheet_abilities=(_lithe_agility_ability(),),
    )
    unit = _unit_for_player(state, player_id="player-a")
    state.gain_faction_resource(
        player_id="player-a",
        resource_kind=PAIN_TOKEN_RESOURCE_KIND,
        amount=1,
        source_id="drukhari-test:lithe-charge-token",
    )
    selection = ChargingUnitSelection(
        player_id="player-a",
        battle_round=state.battle_round,
        unit_instance_id=unit.unit_instance_id,
        request_id="drukhari-test:charge-selection-request",
        result_id="drukhari-test:charge-selection-result",
    )

    grant = army_rule.lithe_agility_charge_declaration_grant(
        ChargeDeclarationContext(
            state=state,
            player_id="player-a",
            battle_round=state.battle_round,
            unit_instance_id=unit.unit_instance_id,
            selection_request_id=selection.request_id,
            selection_result_id=selection.result_id,
        )
    )

    assert grant is not None
    _record_charge_declaration_grant_effects(
        state=state,
        result=DecisionResult(
            result_id="drukhari-test:lithe-charge-grant-result",
            request_id="drukhari-test:lithe-charge-grant-request",
            decision_type=SELECT_CHARGE_DECLARATION_GRANT_DECISION_TYPE,
            actor_id="player-a",
            selected_option_id=grant.hook_id,
            payload=validate_json_value(grant.to_payload()),
        ),
        selection=selection,
        grant=grant,
    )

    permission = _charge_reroll_permission_for_unit(
        state=state,
        player_id="player-a",
        unit_instance_id=unit.unit_instance_id,
        ability_index=AbilityCatalogIndex.from_records(()),
    )

    assert pain_tokens_available(state, player_id="player-a") == 0
    assert permission is not None
    assert permission.source_id.startswith(SOURCE_RULE_ID)


def test_hatred_eternal_selected_to_shoot_requests_player_facing_grant() -> None:
    state = _battle_state()
    _set_current_battle_phase(state, BattlePhase.SHOOTING)
    _mark_player_as_drukhari(
        state,
        player_id="player-a",
        datasheet_abilities=(_hatred_eternal_ability(),),
    )
    unit = _unit_for_player(state, player_id="player-a")
    state.gain_faction_resource(
        player_id="player-a",
        resource_kind=PAIN_TOKEN_RESOURCE_KIND,
        amount=1,
        source_id="drukhari-test:hatred-selected-token",
    )
    decisions = DecisionController()
    selection = ShootingUnitSelection(
        player_id="player-a",
        battle_round=state.battle_round,
        unit_instance_id=unit.unit_instance_id,
        request_id="drukhari-test:shooting-selection-request",
        result_id="drukhari-test:shooting-selection-result",
    )
    registry = ShootingUnitSelectedGrantRegistry.from_bindings(
        army_rule.runtime_contribution().shooting_unit_selected_grant_hook_bindings
    )

    status = _request_shooting_unit_selected_grant_decision_if_available(
        state=state,
        decisions=decisions,
        selection=selection,
        registry=registry,
    )

    assert status is not None
    assert status.status_kind is LifecycleStatusKind.WAITING_FOR_DECISION
    request = status.decision_request
    assert request is not None
    assert request.decision_type == SELECT_SHOOTING_UNIT_GRANT_DECISION_TYPE
    assert {option.option_id for option in request.options} == {
        DECLINE_SHOOTING_UNIT_GRANT_OPTION_ID,
        army_rule.HATRED_ETERNAL_SHOOTING_HOOK_ID,
    }


def test_empty_selected_to_shoot_grant_registry_does_not_request_decision() -> None:
    state = _battle_state()
    _set_current_battle_phase(state, BattlePhase.SHOOTING)
    unit = _unit_for_player(state, player_id="player-a")
    decisions = DecisionController()
    selection = ShootingUnitSelection(
        player_id="player-a",
        battle_round=state.battle_round,
        unit_instance_id=unit.unit_instance_id,
        request_id="drukhari-test:empty-shooting-selection-request",
        result_id="drukhari-test:empty-shooting-selection-result",
    )

    status = _request_shooting_unit_selected_grant_decision_if_available(
        state=state,
        decisions=decisions,
        selection=selection,
        registry=ShootingUnitSelectedGrantRegistry.empty(),
    )

    assert status is None
    assert decisions.queue.pending_requests == ()


def test_selected_to_shoot_grant_registry_validates_handler_contract() -> None:
    state = _battle_state()
    _set_current_battle_phase(state, BattlePhase.SHOOTING)
    unit = _unit_for_player(state, player_id="player-a")
    context = ShootingUnitSelectedContext(
        state=state,
        player_id="player-a",
        battle_round=state.battle_round,
        unit_instance_id=unit.unit_instance_id,
        request_id="drukhari-test:registry-request",
        result_id="drukhari-test:registry-result",
    )

    with pytest.raises(GameLifecycleError, match="handler must be callable"):
        ShootingUnitSelectedGrantBinding(
            hook_id="drukhari-test:not-callable",
            source_id="drukhari-test:not-callable-source",
            handler=cast(
                Callable[[ShootingUnitSelectedContext], ShootingUnitSelectedGrant | None],
                object(),
            ),
        )
    with pytest.raises(GameLifecycleError, match="grant hooks require a context"):
        ShootingUnitSelectedGrantRegistry.empty().grants_for(
            cast(ShootingUnitSelectedContext, object())
        )
    with pytest.raises(GameLifecycleError, match="bindings must be a tuple"):
        ShootingUnitSelectedGrantRegistry(
            bindings=cast(tuple[ShootingUnitSelectedGrantBinding, ...], [])
        )
    with pytest.raises(GameLifecycleError, match="must contain ShootingUnitSelectedGrantBinding"):
        ShootingUnitSelectedGrantRegistry.from_bindings(
            cast(tuple[ShootingUnitSelectedGrantBinding, ...], (object(),))
        )

    def no_grant(_: ShootingUnitSelectedContext) -> None:
        return None

    empty_binding = ShootingUnitSelectedGrantBinding(
        hook_id="drukhari-test:registry-none",
        source_id="drukhari-test:registry-source",
        handler=no_grant,
    )
    assert (
        ShootingUnitSelectedGrantRegistry.from_bindings((empty_binding,)).grants_for(context) == ()
    )

    with pytest.raises(GameLifecycleError, match="hook IDs must be unique"):
        ShootingUnitSelectedGrantRegistry.from_bindings((empty_binding, empty_binding))
    with pytest.raises(GameLifecycleError, match="expiration requires an effect"):
        ShootingUnitSelectedGrant(
            hook_id="drukhari-test:bad-expiration",
            source_id="drukhari-test:bad-expiration-source",
            label="Bad expiration",
            unit_effect_expiration="end_phase",
        )
    with pytest.raises(GameLifecycleError, match="effect requires expiration"):
        ShootingUnitSelectedGrant(
            hook_id="drukhari-test:bad-effect",
            source_id="drukhari-test:bad-effect-source",
            label="Bad effect",
            unit_effect_payload={"effect_kind": "drukhari-test:effect"},
        )
    with pytest.raises(GameLifecycleError, match="end_phase or end_turn"):
        ShootingUnitSelectedGrant(
            hook_id="drukhari-test:bad-expiration-token",
            source_id="drukhari-test:bad-expiration-token-source",
            label="Bad expiration token",
            unit_effect_payload={"effect_kind": "drukhari-test:effect"},
            unit_effect_expiration="end_battle_round",
        )

    def wrong_type(_: ShootingUnitSelectedContext) -> ShootingUnitSelectedGrant:
        return cast(ShootingUnitSelectedGrant, object())

    with pytest.raises(GameLifecycleError, match="handlers must return grants or None"):
        ShootingUnitSelectedGrantRegistry.from_bindings(
            (
                ShootingUnitSelectedGrantBinding(
                    hook_id="drukhari-test:wrong-type",
                    source_id="drukhari-test:wrong-type-source",
                    handler=wrong_type,
                ),
            )
        ).grants_for(context)

    def hook_drift(_: ShootingUnitSelectedContext) -> ShootingUnitSelectedGrant:
        return ShootingUnitSelectedGrant(
            hook_id="drukhari-test:drifted-hook",
            source_id="drukhari-test:hook-source",
            label="Hook drift",
        )

    with pytest.raises(GameLifecycleError, match="hook_id drift"):
        ShootingUnitSelectedGrantRegistry.from_bindings(
            (
                ShootingUnitSelectedGrantBinding(
                    hook_id="drukhari-test:hook",
                    source_id="drukhari-test:hook-source",
                    handler=hook_drift,
                ),
            )
        ).grants_for(context)

    def source_drift(_: ShootingUnitSelectedContext) -> ShootingUnitSelectedGrant:
        return ShootingUnitSelectedGrant(
            hook_id="drukhari-test:source",
            source_id="drukhari-test:drifted-source",
            label="Source drift",
        )

    with pytest.raises(GameLifecycleError, match="source_id drift"):
        ShootingUnitSelectedGrantRegistry.from_bindings(
            (
                ShootingUnitSelectedGrantBinding(
                    hook_id="drukhari-test:source",
                    source_id="drukhari-test:source-rule",
                    handler=source_drift,
                ),
            )
        ).grants_for(context)


def test_selected_to_fight_grant_registry_validates_handler_contract() -> None:
    state = _battle_state()
    _set_current_battle_phase(state, BattlePhase.FIGHT)
    unit = _unit_for_player(state, player_id="player-a")
    context = FightUnitSelectedContext(
        state=state,
        player_id="player-a",
        battle_round=state.battle_round,
        unit_instance_id=unit.unit_instance_id,
        fight_type="normal",
        ordering_band="remaining_combats",
        request_id="drukhari-test:fight-registry-request",
        result_id="drukhari-test:fight-registry-result",
    )

    with pytest.raises(GameLifecycleError, match="state must be a GameState"):
        FightUnitSelectedContext(
            state=cast(GameState, object()),
            player_id="player-a",
            battle_round=state.battle_round,
            unit_instance_id=unit.unit_instance_id,
            fight_type="normal",
            ordering_band="remaining_combats",
            request_id="drukhari-test:fight-registry-request",
            result_id="drukhari-test:fight-registry-result",
        )
    shooting_state = _battle_state()
    _set_current_battle_phase(shooting_state, BattlePhase.SHOOTING)
    with pytest.raises(GameLifecycleError, match="requires the Fight phase"):
        FightUnitSelectedContext(
            state=shooting_state,
            player_id="player-a",
            battle_round=shooting_state.battle_round,
            unit_instance_id=unit.unit_instance_id,
            fight_type="normal",
            ordering_band="remaining_combats",
            request_id="drukhari-test:fight-registry-request",
            result_id="drukhari-test:fight-registry-result",
        )
    with pytest.raises(GameLifecycleError, match="handler must be callable"):
        FightUnitSelectedGrantBinding(
            hook_id="drukhari-test:fight-not-callable",
            source_id="drukhari-test:fight-not-callable-source",
            handler=cast(
                Callable[[FightUnitSelectedContext], FightUnitSelectedGrant | None],
                object(),
            ),
        )
    with pytest.raises(GameLifecycleError, match="grant hooks require a context"):
        FightUnitSelectedGrantRegistry.empty().grants_for(cast(FightUnitSelectedContext, object()))
    with pytest.raises(GameLifecycleError, match="bindings must be a tuple"):
        FightUnitSelectedGrantRegistry(bindings=cast(tuple[FightUnitSelectedGrantBinding, ...], []))
    with pytest.raises(GameLifecycleError, match="must contain FightUnitSelectedGrantBinding"):
        FightUnitSelectedGrantRegistry.from_bindings(
            cast(tuple[FightUnitSelectedGrantBinding, ...], (object(),))
        )

    def no_grant(_: FightUnitSelectedContext) -> None:
        return None

    empty_binding = FightUnitSelectedGrantBinding(
        hook_id="drukhari-test:fight-registry-none",
        source_id="drukhari-test:fight-registry-source",
        handler=no_grant,
    )
    assert FightUnitSelectedGrantRegistry.from_bindings((empty_binding,)).grants_for(context) == ()

    with pytest.raises(GameLifecycleError, match="hook IDs must be unique"):
        FightUnitSelectedGrantRegistry.from_bindings((empty_binding, empty_binding))
    with pytest.raises(GameLifecycleError, match="expiration requires an effect"):
        FightUnitSelectedGrant(
            hook_id="drukhari-test:fight-bad-expiration",
            source_id="drukhari-test:fight-bad-expiration-source",
            label="Bad expiration",
            unit_effect_expiration="end_phase",
        )
    with pytest.raises(GameLifecycleError, match="effect requires expiration"):
        FightUnitSelectedGrant(
            hook_id="drukhari-test:fight-bad-effect",
            source_id="drukhari-test:fight-bad-effect-source",
            label="Bad effect",
            unit_effect_payload={"effect_kind": "drukhari-test:effect"},
        )
    with pytest.raises(GameLifecycleError, match="end_phase or end_turn"):
        FightUnitSelectedGrant(
            hook_id="drukhari-test:fight-bad-expiration-token",
            source_id="drukhari-test:fight-bad-expiration-token-source",
            label="Bad expiration token",
            unit_effect_payload={"effect_kind": "drukhari-test:effect"},
            unit_effect_expiration="end_battle_round",
        )
    with pytest.raises(GameLifecycleError, match="must be a string"):
        FightUnitSelectedGrant(
            hook_id=cast(str, 1),
            source_id="drukhari-test:fight-bad-hook-source",
            label="Bad hook",
        )
    with pytest.raises(GameLifecycleError, match="must not be empty"):
        FightUnitSelectedGrant(
            hook_id=" ",
            source_id="drukhari-test:fight-empty-hook-source",
            label="Empty hook",
        )
    with pytest.raises(GameLifecycleError, match="must be an int"):
        FightUnitSelectedContext(
            state=state,
            player_id="player-a",
            battle_round=cast(int, "1"),
            unit_instance_id=unit.unit_instance_id,
            fight_type="normal",
            ordering_band="remaining_combats",
            request_id="drukhari-test:fight-registry-request",
            result_id="drukhari-test:fight-registry-result",
        )
    with pytest.raises(GameLifecycleError, match="must be positive"):
        FightUnitSelectedContext(
            state=state,
            player_id="player-a",
            battle_round=0,
            unit_instance_id=unit.unit_instance_id,
            fight_type="normal",
            ordering_band="remaining_combats",
            request_id="drukhari-test:fight-registry-request",
            result_id="drukhari-test:fight-registry-result",
        )

    def wrong_type(_: FightUnitSelectedContext) -> FightUnitSelectedGrant:
        return cast(FightUnitSelectedGrant, object())

    with pytest.raises(GameLifecycleError, match="handlers must return grants or None"):
        FightUnitSelectedGrantRegistry.from_bindings(
            (
                FightUnitSelectedGrantBinding(
                    hook_id="drukhari-test:fight-wrong-type",
                    source_id="drukhari-test:fight-wrong-type-source",
                    handler=wrong_type,
                ),
            )
        ).grants_for(context)

    def hook_drift(_: FightUnitSelectedContext) -> FightUnitSelectedGrant:
        return FightUnitSelectedGrant(
            hook_id="drukhari-test:fight-drifted-hook",
            source_id="drukhari-test:fight-hook-source",
            label="Hook drift",
        )

    with pytest.raises(GameLifecycleError, match="hook_id drift"):
        FightUnitSelectedGrantRegistry.from_bindings(
            (
                FightUnitSelectedGrantBinding(
                    hook_id="drukhari-test:fight-hook",
                    source_id="drukhari-test:fight-hook-source",
                    handler=hook_drift,
                ),
            )
        ).grants_for(context)

    def source_drift(_: FightUnitSelectedContext) -> FightUnitSelectedGrant:
        return FightUnitSelectedGrant(
            hook_id="drukhari-test:fight-source",
            source_id="drukhari-test:fight-drifted-source",
            label="Source drift",
        )

    with pytest.raises(GameLifecycleError, match="source_id drift"):
        FightUnitSelectedGrantRegistry.from_bindings(
            (
                FightUnitSelectedGrantBinding(
                    hook_id="drukhari-test:fight-source",
                    source_id="drukhari-test:fight-source-rule",
                    handler=source_drift,
                ),
            )
        ).grants_for(context)


def test_hatred_eternal_grant_spends_pain_token_and_unlocks_hit_reroll() -> None:
    state = _battle_state()
    _set_current_battle_phase(state, BattlePhase.SHOOTING)
    _mark_player_as_drukhari(
        state,
        player_id="player-a",
        datasheet_abilities=(_hatred_eternal_ability(),),
    )
    unit = _unit_for_player(state, player_id="player-a")
    state.gain_faction_resource(
        player_id="player-a",
        resource_kind=PAIN_TOKEN_RESOURCE_KIND,
        amount=1,
        source_id="drukhari-test:hatred-token",
    )

    decisions = DecisionController()
    selection = ShootingUnitSelection(
        player_id="player-a",
        battle_round=state.battle_round,
        unit_instance_id=unit.unit_instance_id,
        request_id="drukhari-test:hatred-selection-request",
        result_id="drukhari-test:hatred-selection-result",
    )
    state.shooting_phase_state = ShootingPhaseState(
        battle_round=state.battle_round,
        active_player_id="player-a",
    ).with_unit_selection(selection)
    registry = ShootingUnitSelectedGrantRegistry.from_bindings(
        army_rule.runtime_contribution().shooting_unit_selected_grant_hook_bindings
    )
    handler = _shooting_phase_handler(registry)
    status = _request_shooting_unit_selected_grant_decision_if_available(
        state=state,
        decisions=decisions,
        selection=selection,
        registry=registry,
    )
    assert status is not None
    request = status.decision_request
    assert request is not None
    result = DecisionResult.for_request(
        result_id="drukhari-test:hatred-grant-result",
        request=request,
        selected_option_id=army_rule.HATRED_ETERNAL_SHOOTING_HOOK_ID,
    )

    invalid = handler.invalid_shooting_unit_selected_grant_status(
        state=state,
        request=request,
        result=result,
    )
    assert invalid is None
    assert handler.apply_decision(state=state, result=result, decisions=decisions) is None
    permission = source_backed_reroll_permission_for_unit(
        state=state,
        player_id="player-a",
        unit_instance_id=unit.unit_instance_id,
        roll_type="attack_sequence.hit",
        timing_window="attack_sequence.hit",
    )

    assert pain_tokens_available(state, player_id="player-a") == 0
    assert permission is not None
    assert permission.source_id.startswith(SOURCE_RULE_ID)
    assert unit_is_empowered_through_pain_for_ability(
        state=state,
        player_id="player-a",
        unit_instance_id=unit.unit_instance_id,
        pain_ability_key=HATRED_ETERNAL_ABILITY_KEY,
    )
    resolved_events = [
        record
        for record in decisions.event_log.records
        if record.event_type == "shooting_unit_selected_grant_decision_resolved"
    ]
    assert len(resolved_events) == 1


def test_hatred_eternal_grant_prevalidation_rejects_payload_drift() -> None:
    state = _battle_state()
    _set_current_battle_phase(state, BattlePhase.SHOOTING)
    _mark_player_as_drukhari(
        state,
        player_id="player-a",
        datasheet_abilities=(_hatred_eternal_ability(),),
    )
    unit = _unit_for_player(state, player_id="player-a")
    state.gain_faction_resource(
        player_id="player-a",
        resource_kind=PAIN_TOKEN_RESOURCE_KIND,
        amount=1,
        source_id="drukhari-test:hatred-drift-token",
    )
    decisions = DecisionController()
    selection = ShootingUnitSelection(
        player_id="player-a",
        battle_round=state.battle_round,
        unit_instance_id=unit.unit_instance_id,
        request_id="drukhari-test:hatred-drift-selection-request",
        result_id="drukhari-test:hatred-drift-selection-result",
    )
    state.shooting_phase_state = ShootingPhaseState(
        battle_round=state.battle_round,
        active_player_id="player-a",
    ).with_unit_selection(selection)
    registry = ShootingUnitSelectedGrantRegistry.from_bindings(
        army_rule.runtime_contribution().shooting_unit_selected_grant_hook_bindings
    )
    status = _request_shooting_unit_selected_grant_decision_if_available(
        state=state,
        decisions=decisions,
        selection=selection,
        registry=registry,
    )
    assert status is not None
    request = status.decision_request
    assert request is not None
    result = DecisionResult.for_request(
        result_id="drukhari-test:hatred-drift-grant-result",
        request=request,
        selected_option_id=army_rule.HATRED_ETERNAL_SHOOTING_HOOK_ID,
    )
    result_payload = result.payload
    assert isinstance(result_payload, dict)
    selected_grants = result_payload["selected_shooting_unit_grants"]
    assert isinstance(selected_grants, list)
    selected_grant = selected_grants[0]
    assert isinstance(selected_grant, dict)
    drifted_grant = dict(selected_grant)
    drifted_grant["label"] = "Drifted Hatred Eternal"
    drifted_payload = dict(result_payload)
    drifted_payload["selected_shooting_unit_grants"] = [drifted_grant]
    drifted_result = DecisionResult(
        result_id=result.result_id,
        request_id=result.request_id,
        decision_type=result.decision_type,
        actor_id=result.actor_id,
        selected_option_id=result.selected_option_id,
        payload=validate_json_value(drifted_payload),
    )
    invalid = _shooting_phase_handler(registry).invalid_shooting_unit_selected_grant_status(
        state=state,
        request=request,
        result=drifted_result,
    )

    assert invalid is not None
    assert invalid.status_kind is LifecycleStatusKind.INVALID
    assert pain_tokens_available(state, player_id="player-a") == 1


def test_hatred_eternal_grant_prevalidation_rejects_context_and_shape_drift() -> None:
    state = _battle_state()
    _set_current_battle_phase(state, BattlePhase.SHOOTING)
    _mark_player_as_drukhari(
        state,
        player_id="player-a",
        datasheet_abilities=(_hatred_eternal_ability(),),
    )
    unit = _unit_for_player(state, player_id="player-a")
    state.gain_faction_resource(
        player_id="player-a",
        resource_kind=PAIN_TOKEN_RESOURCE_KIND,
        amount=1,
        source_id="drukhari-test:hatred-shape-token",
    )
    decisions = DecisionController()
    selection = ShootingUnitSelection(
        player_id="player-a",
        battle_round=state.battle_round,
        unit_instance_id=unit.unit_instance_id,
        request_id="drukhari-test:hatred-shape-selection-request",
        result_id="drukhari-test:hatred-shape-selection-result",
    )
    selected_state = ShootingPhaseState(
        battle_round=state.battle_round,
        active_player_id="player-a",
    ).with_unit_selection(selection)
    state.shooting_phase_state = selected_state
    registry = ShootingUnitSelectedGrantRegistry.from_bindings(
        army_rule.runtime_contribution().shooting_unit_selected_grant_hook_bindings
    )
    handler = _shooting_phase_handler(registry)
    status = _request_shooting_unit_selected_grant_decision_if_available(
        state=state,
        decisions=decisions,
        selection=selection,
        registry=registry,
    )
    assert status is not None
    request = status.decision_request
    assert request is not None
    result = DecisionResult.for_request(
        result_id="drukhari-test:hatred-shape-grant-result",
        request=request,
        selected_option_id=army_rule.HATRED_ETERNAL_SHOOTING_HOOK_ID,
    )
    result_payload = result.payload
    assert isinstance(result_payload, dict)
    selected_grants = result_payload["selected_shooting_unit_grants"]
    assert isinstance(selected_grants, list)
    selected_grant = selected_grants[0]
    assert isinstance(selected_grant, dict)

    wrong_type_request = DecisionRequest(
        request_id=request.request_id,
        decision_type="drukhari-test:wrong-decision-type",
        actor_id=request.actor_id,
        payload=request.payload,
        options=request.options,
    )
    with pytest.raises(GameLifecycleError, match="unsupported decision_type"):
        handler.invalid_shooting_unit_selected_grant_status(
            state=state,
            request=wrong_type_request,
            result=result,
        )

    state.shooting_phase_state = ShootingPhaseState(
        battle_round=state.battle_round,
        active_player_id="player-a",
    )
    invalid = handler.invalid_shooting_unit_selected_grant_status(
        state=state,
        request=request,
        result=result,
    )
    assert invalid is not None
    assert invalid.status_kind is LifecycleStatusKind.INVALID
    state.shooting_phase_state = selected_state

    wrong_actor = DecisionResult(
        result_id=result.result_id,
        request_id=result.request_id,
        decision_type=result.decision_type,
        actor_id="player-b",
        selected_option_id=result.selected_option_id,
        payload=result.payload,
    )
    with pytest.raises(GameLifecycleError, match="actor must be the selected unit player"):
        handler.apply_decision(state=state, result=wrong_actor, decisions=decisions)

    for drifted_payload in (
        {**result_payload, "unit_instance_id": "drukhari-test:wrong-unit"},
        {**result_payload, "source_decision_request_id": "drukhari-test:wrong-request"},
        {
            key: value
            for key, value in result_payload.items()
            if key != "selected_shooting_unit_grants"
        },
        {**result_payload, "selected_shooting_unit_grants": [None]},
        {**result_payload, "selected_shooting_unit_grants": []},
        {
            **result_payload,
            "selected_shooting_unit_grants": [
                {**selected_grant, "hook_id": "drukhari-test:unavailable-grant"}
            ],
        },
    ):
        drifted = DecisionResult(
            result_id=result.result_id,
            request_id=result.request_id,
            decision_type=result.decision_type,
            actor_id=result.actor_id,
            selected_option_id=result.selected_option_id,
            payload=validate_json_value(drifted_payload),
        )
        invalid = handler.invalid_shooting_unit_selected_grant_status(
            state=state,
            request=request,
            result=drifted,
        )
        assert invalid is not None
        assert invalid.status_kind is LifecycleStatusKind.INVALID

    assert pain_tokens_available(state, player_id="player-a") == 1


def test_hatred_eternal_grant_decline_spends_no_pain_token() -> None:
    state = _battle_state()
    _set_current_battle_phase(state, BattlePhase.SHOOTING)
    _mark_player_as_drukhari(
        state,
        player_id="player-a",
        datasheet_abilities=(_hatred_eternal_ability(),),
    )
    unit = _unit_for_player(state, player_id="player-a")
    state.gain_faction_resource(
        player_id="player-a",
        resource_kind=PAIN_TOKEN_RESOURCE_KIND,
        amount=1,
        source_id="drukhari-test:hatred-decline-token",
    )
    decisions = DecisionController()
    selection = ShootingUnitSelection(
        player_id="player-a",
        battle_round=state.battle_round,
        unit_instance_id=unit.unit_instance_id,
        request_id="drukhari-test:hatred-decline-selection-request",
        result_id="drukhari-test:hatred-decline-selection-result",
    )
    state.shooting_phase_state = ShootingPhaseState(
        battle_round=state.battle_round,
        active_player_id="player-a",
    ).with_unit_selection(selection)
    registry = ShootingUnitSelectedGrantRegistry.from_bindings(
        army_rule.runtime_contribution().shooting_unit_selected_grant_hook_bindings
    )
    handler = _shooting_phase_handler(registry)
    status = _request_shooting_unit_selected_grant_decision_if_available(
        state=state,
        decisions=decisions,
        selection=selection,
        registry=registry,
    )
    assert status is not None
    request = status.decision_request
    assert request is not None
    result = DecisionResult.for_request(
        result_id="drukhari-test:hatred-decline-grant-result",
        request=request,
        selected_option_id=DECLINE_SHOOTING_UNIT_GRANT_OPTION_ID,
    )

    invalid = handler.invalid_shooting_unit_selected_grant_status(
        state=state,
        request=request,
        result=result,
    )
    assert invalid is None
    assert handler.apply_decision(state=state, result=result, decisions=decisions) is None
    assert pain_tokens_available(state, player_id="player-a") == 1
    assert (
        source_backed_reroll_permission_for_unit(
            state=state,
            player_id="player-a",
            unit_instance_id=unit.unit_instance_id,
            roll_type="attack_sequence.hit",
            timing_window="attack_sequence.hit",
        )
        is None
    )


def test_hatred_eternal_decline_rejects_selected_grant_payload() -> None:
    state = _battle_state()
    _set_current_battle_phase(state, BattlePhase.SHOOTING)
    _mark_player_as_drukhari(
        state,
        player_id="player-a",
        datasheet_abilities=(_hatred_eternal_ability(),),
    )
    unit = _unit_for_player(state, player_id="player-a")
    state.gain_faction_resource(
        player_id="player-a",
        resource_kind=PAIN_TOKEN_RESOURCE_KIND,
        amount=1,
        source_id="drukhari-test:hatred-decline-drift-token",
    )
    decisions = DecisionController()
    selection = ShootingUnitSelection(
        player_id="player-a",
        battle_round=state.battle_round,
        unit_instance_id=unit.unit_instance_id,
        request_id="drukhari-test:hatred-decline-drift-selection-request",
        result_id="drukhari-test:hatred-decline-drift-selection-result",
    )
    state.shooting_phase_state = ShootingPhaseState(
        battle_round=state.battle_round,
        active_player_id="player-a",
    ).with_unit_selection(selection)
    registry = ShootingUnitSelectedGrantRegistry.from_bindings(
        army_rule.runtime_contribution().shooting_unit_selected_grant_hook_bindings
    )
    status = _request_shooting_unit_selected_grant_decision_if_available(
        state=state,
        decisions=decisions,
        selection=selection,
        registry=registry,
    )
    assert status is not None
    request = status.decision_request
    assert request is not None
    grant_payload = request.option_by_id(army_rule.HATRED_ETERNAL_SHOOTING_HOOK_ID).payload
    assert isinstance(grant_payload, dict)
    selected_grants = grant_payload["selected_shooting_unit_grants"]
    assert isinstance(selected_grants, list)
    decline = DecisionResult.for_request(
        result_id="drukhari-test:hatred-decline-drift-result",
        request=request,
        selected_option_id=DECLINE_SHOOTING_UNIT_GRANT_OPTION_ID,
    )
    decline_payload = decline.payload
    assert isinstance(decline_payload, dict)
    drifted_payload = dict(decline_payload)
    drifted_payload["selected_shooting_unit_grants"] = selected_grants
    drifted_decline = DecisionResult(
        result_id=decline.result_id,
        request_id=decline.request_id,
        decision_type=decline.decision_type,
        actor_id=decline.actor_id,
        selected_option_id=decline.selected_option_id,
        payload=validate_json_value(drifted_payload),
    )
    invalid = _shooting_phase_handler(registry).invalid_shooting_unit_selected_grant_status(
        state=state,
        request=request,
        result=drifted_decline,
    )

    assert invalid is not None
    assert invalid.status_kind is LifecycleStatusKind.INVALID
    assert pain_tokens_available(state, player_id="player-a") == 1


def test_selected_to_shoot_grant_effect_recording_validates_unit_effect_payload() -> None:
    state = _battle_state()
    _set_current_battle_phase(state, BattlePhase.SHOOTING)
    unit = _unit_for_player(state, player_id="player-a")
    target_unit = _unit_for_player(state, player_id="player-b")
    selection = ShootingUnitSelection(
        player_id="player-a",
        battle_round=state.battle_round,
        unit_instance_id=unit.unit_instance_id,
        request_id="drukhari-test:effect-selection-request",
        result_id="drukhari-test:effect-selection-result",
    )

    def record_grant(
        *,
        grant_id: str,
        unit_effect_payload: JsonValue,
        unit_effect_expiration: str,
    ) -> PersistingEffect:
        effects = _record_shooting_unit_selected_grant_effects(
            state=state,
            result=DecisionResult(
                result_id=f"drukhari-test:{grant_id}-result",
                request_id=f"drukhari-test:{grant_id}-request",
                decision_type=SELECT_SHOOTING_UNIT_GRANT_DECISION_TYPE,
                actor_id="player-a",
                selected_option_id=f"drukhari-test:{grant_id}",
                payload={"submission_kind": SELECT_SHOOTING_UNIT_GRANT_DECISION_TYPE},
            ),
            selection=selection,
            grant=ShootingUnitSelectedGrant(
                hook_id=f"drukhari-test:{grant_id}",
                source_id=f"drukhari-test:{grant_id}-source",
                label=f"Grant {grant_id}",
                unit_effect_payload=unit_effect_payload,
                unit_effect_expiration=unit_effect_expiration,
            ),
        )
        assert len(effects) == 1
        return effects[0]

    string_payload_effect = record_grant(
        grant_id="string-effect",
        unit_effect_payload="drukhari-test:string-effect",
        unit_effect_expiration="end_phase",
    )
    assert string_payload_effect.target_unit_instance_ids == (unit.unit_instance_id,)

    targetless_payload_effect = record_grant(
        grant_id="targetless-effect",
        unit_effect_payload={"effect_kind": "drukhari-test:targetless-effect"},
        unit_effect_expiration="end_phase",
    )
    assert targetless_payload_effect.target_unit_instance_ids == (unit.unit_instance_id,)

    end_turn_effect = record_grant(
        grant_id="end-turn-effect",
        unit_effect_payload={
            "effect_kind": "drukhari-test:end-turn-effect",
            "target_unit_instance_ids": [target_unit.unit_instance_id],
        },
        unit_effect_expiration="end_turn",
    )
    assert end_turn_effect.target_unit_instance_ids == (target_unit.unit_instance_id,)
    assert end_turn_effect.expiration.expiration_kind.value == "end_turn"

    bad_cases: tuple[tuple[JsonValue, str], ...] = (
        (
            validate_json_value(
                {
                    "effect_kind": "drukhari-test:bad-target-type",
                    "target_unit_instance_ids": unit.unit_instance_id,
                }
            ),
            "must be a list",
        ),
        (
            validate_json_value(
                {
                    "effect_kind": "drukhari-test:empty-targets",
                    "target_unit_instance_ids": [],
                }
            ),
            "is empty",
        ),
        (
            validate_json_value(
                {
                    "effect_kind": "drukhari-test:duplicate-targets",
                    "target_unit_instance_ids": [unit.unit_instance_id, unit.unit_instance_id],
                }
            ),
            "are duplicated",
        ),
    )
    for bad_payload, message in bad_cases:
        with pytest.raises(GameLifecycleError, match=message):
            record_grant(
                grant_id=f"bad-{message.replace(' ', '-')}",
                unit_effect_payload=bad_payload,
                unit_effect_expiration="end_phase",
            )

    with pytest.raises(GameLifecycleError, match="no effect to record"):
        _record_shooting_unit_selected_grant_effects(
            state=state,
            result=DecisionResult(
                result_id="drukhari-test:no-effect-result",
                request_id="drukhari-test:no-effect-request",
                decision_type=SELECT_SHOOTING_UNIT_GRANT_DECISION_TYPE,
                actor_id="player-a",
                selected_option_id="drukhari-test:no-effect",
                payload={"submission_kind": SELECT_SHOOTING_UNIT_GRANT_DECISION_TYPE},
            ),
            selection=selection,
            grant=ShootingUnitSelectedGrant(
                hook_id="drukhari-test:no-effect",
                source_id="drukhari-test:no-effect-source",
                label="No effect",
            ),
        )


def test_hatred_eternal_hit_reroll_uses_attack_sequence_dice_reroll_request() -> None:
    state = _battle_state()
    _set_current_battle_phase(state, BattlePhase.SHOOTING)
    _mark_player_as_drukhari(
        state,
        player_id="player-a",
        datasheet_abilities=(_hatred_eternal_ability(),),
    )
    unit = _unit_for_player(state, player_id="player-a")
    state.gain_faction_resource(
        player_id="player-a",
        resource_kind=PAIN_TOKEN_RESOURCE_KIND,
        amount=1,
        source_id="drukhari-test:hatred-attack-token",
    )
    grant = army_rule.hatred_eternal_shooting_unit_selected_grant(
        ShootingUnitSelectedContext(
            state=state,
            player_id="player-a",
            battle_round=state.battle_round,
            unit_instance_id=unit.unit_instance_id,
            request_id="drukhari-test:hatred-attack-selection-request",
            result_id="drukhari-test:hatred-attack-selection-result",
        )
    )
    assert grant is not None
    _record_shooting_unit_selected_grant_effects(
        state=state,
        result=DecisionResult(
            result_id="drukhari-test:hatred-attack-grant-result",
            request_id="drukhari-test:hatred-attack-grant-request",
            decision_type=SELECT_SHOOTING_UNIT_GRANT_DECISION_TYPE,
            actor_id="player-a",
            selected_option_id=grant.hook_id,
            payload=validate_json_value(grant.to_payload()),
        ),
        selection=ShootingUnitSelection(
            player_id="player-a",
            battle_round=state.battle_round,
            unit_instance_id=unit.unit_instance_id,
            request_id="drukhari-test:hatred-attack-selection-request",
            result_id="drukhari-test:hatred-attack-selection-result",
        ),
        grant=grant,
    )
    decisions = DecisionController()
    manager = DiceRollManager(state.game_id, event_log=decisions.event_log)
    roll_state = manager.roll_fixed(
        attack_sequence_hit_roll_spec(
            weapon_profile_id="drukhari-test-splinter-rifle",
            attack_context_id="drukhari-test:attack-context",
            attacker_player_id="player-a",
        ),
        [2],
    )

    status = _request_source_backed_hit_reroll_if_available(
        state=state,
        decisions=decisions,
        roll_state=roll_state,
        attacking_unit_instance_id=unit.unit_instance_id,
        attack_context_id="drukhari-test:attack-context",
        source_phase=BattlePhase.SHOOTING,
        weapon_profile_id="drukhari-test-splinter-rifle",
    )

    assert status is not None
    request = status.decision_request
    assert request is not None
    assert request.decision_type == DICE_REROLL_DECISION_TYPE
    payload = request.payload
    assert isinstance(payload, dict)
    permission_payload = payload["permission"]
    assert isinstance(permission_payload, dict)
    source_id = permission_payload["source_id"]
    assert isinstance(source_id, str)
    assert source_id.startswith(SOURCE_RULE_ID)

    decline = DecisionResult.for_request(
        result_id="drukhari-test:hatred-reroll-decline",
        request=request,
        selected_option_id="decline",
    )
    decisions.submit_result(decline)
    repeated_status = _request_source_backed_hit_reroll_if_available(
        state=state,
        decisions=decisions,
        roll_state=roll_state,
        attacking_unit_instance_id=unit.unit_instance_id,
        attack_context_id="drukhari-test:attack-context",
        source_phase=BattlePhase.SHOOTING,
        weapon_profile_id="drukhari-test-splinter-rifle",
    )

    assert repeated_status is None


def test_hatred_eternal_accepted_hit_reroll_resumes_attack_sequence_with_rerolled_hit() -> None:
    base_profile = _weapon_profile_by_wargear(
        wargear_id="core-bolt-rifle",
        weapon_profile_id="core-bolt-rifle:standard",
    )
    hatred_profile = replace(
        base_profile,
        profile_id="drukhari-test-hatred-eternal-rifle",
        name="Hatred Eternal regression rifle",
        attack_profile=AttackProfile.fixed(1),
        skill=CharacteristicValue.from_raw(Characteristic.BALLISTIC_SKILL, 2),
        strength=CharacteristicValue.from_raw(Characteristic.STRENGTH, 12),
        keywords=(),
        abilities=(),
    )
    lifecycle, units = _shooting_lifecycle(
        alpha_unit_ids=("intercessor-1",),
        game_id="drukhari-test-hatred-eternal-consumer",
        catalog=_catalog_with_replaced_bolt_profiles((hatred_profile,)),
    )
    state = _lifecycle_state(lifecycle)
    _mark_player_as_drukhari(
        state,
        player_id="player-a",
        datasheet_abilities=(_hatred_eternal_ability(),),
    )
    unit = _unit_for_player(state, player_id="player-a")
    target_unit = units["enemy"]
    state.gain_faction_resource(
        player_id="player-a",
        resource_kind=PAIN_TOKEN_RESOURCE_KIND,
        amount=1,
        source_id="drukhari-test:hatred-consumer-token",
    )
    _refresh_lifecycle_runtime_content(lifecycle)

    selection_request = _decision_request_from_status(
        lifecycle.advance_until_decision_or_terminal()
    )
    assert selection_request.decision_type == SELECT_SHOOTING_UNIT_DECISION_TYPE
    grant_request = _decision_request_from_status(
        lifecycle.submit_decision(
            DecisionResult.for_request(
                result_id="drukhari-test:hatred-consumer-select-unit",
                request=selection_request,
                selected_option_id=unit.unit_instance_id,
            )
        )
    )
    assert grant_request.decision_type == SELECT_SHOOTING_UNIT_GRANT_DECISION_TYPE
    type_request = _decision_request_from_status(
        lifecycle.submit_decision(
            DecisionResult.for_request(
                result_id="drukhari-test:hatred-consumer-accept-grant",
                request=grant_request,
                selected_option_id=army_rule.HATRED_ETERNAL_SHOOTING_HOOK_ID,
            )
        )
    )
    assert type_request.decision_type == SELECT_SHOOTING_TYPE_DECISION_TYPE
    assert pain_tokens_available(state, player_id="player-a") == 0

    declaration_request = _decision_request_from_status(
        lifecycle.submit_decision(
            DecisionResult.for_request(
                result_id="drukhari-test:hatred-consumer-shooting-type",
                request=type_request,
                selected_option_id="normal",
            )
        )
    )
    assert declaration_request.decision_type == SUBMIT_SHOOTING_DECLARATION_DECISION_TYPE
    proposal = _proposal_from_request(
        request=declaration_request,
        target_unit_id=target_unit.unit_instance_id,
        weapon_profile_id=hatred_profile.profile_id,
    )
    declaration_result_id = "drukhari-test:hatred-consumer-declaration"
    sequence_id = f"attack-sequence:{declaration_result_id}"
    attack_context_id = f"{sequence_id}:pool-001:attack-001"
    fixed_rolls = DiceRollManager(state.game_id, event_log=lifecycle.decision_controller.event_log)
    fixed_rolls.roll_fixed(
        attack_sequence_hit_roll_spec(
            weapon_profile_id=hatred_profile.profile_id,
            attack_context_id=attack_context_id,
            attacker_player_id="player-a",
        ),
        [1],
    )
    fixed_rolls.roll_fixed(
        attack_sequence_wound_roll_spec(
            weapon_profile_id=hatred_profile.profile_id,
            attack_context_id=attack_context_id,
            attacker_player_id="player-a",
        ),
        [6],
    )

    reroll_request = _decision_request_from_status(
        lifecycle.submit_decision(
            DecisionResult(
                result_id=declaration_result_id,
                request_id=declaration_request.request_id,
                decision_type=declaration_request.decision_type,
                actor_id=declaration_request.actor_id,
                selected_option_id="submit_parameterized_payload",
                payload=validate_json_value(proposal.to_payload()),
            )
        )
    )
    assert reroll_request.decision_type == DICE_REROLL_DECISION_TYPE
    reroll_request_payload = cast(dict[str, object], reroll_request.payload)
    attack_context_payload = cast(dict[str, object], reroll_request_payload["attack_context"])
    initial_hit_state = DiceRollState.from_payload(
        cast(DiceRollStatePayload, attack_context_payload["hit_roll_state"])
    )
    assert initial_hit_state.current_total == 1

    accepted_status = lifecycle.submit_decision(
        DecisionResult.for_request(
            result_id="drukhari-test:hatred-consumer-accept-reroll",
            request=reroll_request,
            selected_option_id="reroll:0",
        )
    )

    assert accepted_status.status_kind is not LifecycleStatusKind.INVALID
    reroll_payloads = _event_payloads(lifecycle, "dice_reroll_resolved")
    assert len(reroll_payloads) == 1
    rerolled_state = DiceRollState.from_payload(cast(DiceRollStatePayload, reroll_payloads[0]))
    assert rerolled_state.original_result.roll_id == initial_hit_state.original_result.roll_id
    assert rerolled_state.current_total >= 2
    hit_payload = _attack_step_payload(
        _event_payloads(lifecycle, "attack_sequence_step"),
        AttackSequenceStep.HIT,
    )
    resolved_hit = cast(dict[str, object], hit_payload["payload"])
    assert resolved_hit["successful"] is True
    assert resolved_hit["unmodified_roll"] == rerolled_state.current_total
    assert cast(dict[str, object], resolved_hit["roll_state"]) == rerolled_state.to_payload()
    wound_payload = _attack_step_payload(
        _event_payloads(lifecycle, "attack_sequence_step"),
        AttackSequenceStep.WOUND,
    )
    resolved_wound = cast(dict[str, object], wound_payload["payload"])
    assert resolved_wound["successful"] is True


def test_shooting_dice_reroll_branch_accepts_source_backed_wound_payload() -> None:
    state = _battle_state()
    _set_current_battle_phase(state, BattlePhase.SHOOTING)
    attacker = _unit_for_player(state, player_id="player-a")
    defender = _unit_for_player(state, player_id="player-b")
    wargear_id = attacker.wargear_selections[0].wargear_ids[0]
    weapon_profile = _weapon_profile_by_wargear(
        wargear_id=wargear_id,
        weapon_profile_id=None,
    )
    target_model_ids = tuple(model.model_instance_id for model in defender.own_models)
    attack_pool = RangedAttackPool(
        attacker_model_instance_id=attacker.own_models[0].model_instance_id,
        wargear_id=wargear_id,
        weapon_profile_id=weapon_profile.profile_id,
        weapon_profile=weapon_profile,
        target_unit_instance_id=defender.unit_instance_id,
        shooting_type=ShootingType.NORMAL,
        attacks=1,
        target_visible_model_ids=target_model_ids,
        target_in_range_model_ids=target_model_ids,
    )
    attack_sequence = AttackSequence.start(
        sequence_id="drukhari-test:scoped-reroll-sequence",
        attacker_player_id="player-a",
        attacking_unit_instance_id=attacker.unit_instance_id,
        attack_pools=(attack_pool,),
    )
    state.shooting_phase_state = ShootingPhaseState(
        battle_round=state.battle_round,
        active_player_id="player-a",
        selected_unit_ids=(attacker.unit_instance_id,),
        shot_unit_ids=(attacker.unit_instance_id,),
        attack_pools=(attack_pool,),
        attack_sequence=attack_sequence,
    )
    decisions = DecisionController()
    manager = DiceRollManager(state.game_id, event_log=decisions.event_log)
    wound_roll_state = manager.roll_fixed(
        attack_sequence_wound_roll_spec(
            weapon_profile_id=weapon_profile.profile_id,
            attack_context_id=attack_sequence.attack_context_id(),
            attacker_player_id="player-a",
        ),
        [1],
    )
    permission = RerollPermission(
        source_id=SOURCE_RULE_ID,
        timing_window="attack_sequence.wound",
        owning_player_id="player-a",
        eligible_roll_type="attack_sequence.wound",
        component_selection_policy=RerollComponentSelectionPolicy.WHOLE_ROLL,
    )
    request = manager.build_reroll_request(
        wound_roll_state,
        request_id="drukhari-test:scoped-reroll-request",
        actor_id="player-a",
        permission=permission,
        extra_payload={
            "source_rule_id": SOURCE_RULE_ID,
            "attack_context": {
                "game_id": state.game_id,
                "battle_round": state.battle_round,
                "phase": BattlePhase.SHOOTING.value,
                "unit_instance_id": attacker.unit_instance_id,
                "attack_context_id": attack_sequence.attack_context_id(),
                "weapon_profile_id": weapon_profile.profile_id,
                "target_unit_instance_id": defender.unit_instance_id,
                "wound_roll_state": validate_json_value(wound_roll_state.to_payload()),
            },
        },
    )
    decisions.request_decision(request)
    result = DecisionResult.for_request(
        result_id="drukhari-test:scoped-reroll-result",
        request=request,
        selected_option_id="reroll:0",
    )
    decisions.submit_result(result)

    assert (
        _shooting_phase_handler(ShootingUnitSelectedGrantRegistry.empty()).apply_decision(
            state=state,
            result=result,
            decisions=decisions,
        )
        is None
    )
    reroll_payloads = tuple(
        cast(dict[str, object], event.payload)
        for event in decisions.event_log.records
        if event.event_type == "dice_reroll_resolved"
    )
    assert len(reroll_payloads) == 1
    rerolled_state = DiceRollState.from_payload(cast(DiceRollStatePayload, reroll_payloads[0]))
    assert rerolled_state.original_result.roll_id == wound_roll_state.original_result.roll_id

    malformed_decisions = DecisionController()
    request_payload = cast(dict[str, object], request.payload)
    attack_context = dict(cast(dict[str, object], request_payload["attack_context"]))
    del attack_context["wound_roll_state"]
    malformed_request = replace(
        request,
        request_id="drukhari-test:scoped-malformed-reroll-request",
        payload=validate_json_value({**request_payload, "attack_context": attack_context}),
    )
    malformed_decisions.request_decision(malformed_request)
    malformed_result = DecisionResult.for_request(
        result_id="drukhari-test:scoped-malformed-reroll-result",
        request=malformed_request,
        selected_option_id="reroll:0",
    )
    malformed_decisions.submit_result(malformed_result)

    with pytest.raises(GameLifecycleError, match="payload missing wound_roll_state"):
        _shooting_phase_handler(ShootingUnitSelectedGrantRegistry.empty()).apply_decision(
            state=state,
            result=malformed_result,
            decisions=malformed_decisions,
        )


def test_source_backed_attack_reroll_revalidates_current_source_context() -> None:
    state = _battle_state()
    _set_current_battle_phase(state, BattlePhase.SHOOTING)
    attacker = _unit_for_player(state, player_id="player-a")
    defender = _unit_for_player(state, player_id="player-b")
    wargear_id = attacker.wargear_selections[0].wargear_ids[0]
    weapon_profile = _weapon_profile_by_wargear(
        wargear_id=wargear_id,
        weapon_profile_id=None,
    )
    target_model_ids = tuple(model.model_instance_id for model in defender.own_models)
    attack_pool = RangedAttackPool(
        attacker_model_instance_id=attacker.own_models[0].model_instance_id,
        wargear_id=wargear_id,
        weapon_profile_id=weapon_profile.profile_id,
        weapon_profile=weapon_profile,
        target_unit_instance_id=defender.unit_instance_id,
        shooting_type=ShootingType.NORMAL,
        attacks=1,
        target_visible_model_ids=target_model_ids,
        target_in_range_model_ids=target_model_ids,
    )
    attack_sequence = AttackSequence.start(
        sequence_id="drukhari-test:source-drift-sequence",
        attacker_player_id="player-a",
        attacking_unit_instance_id=attacker.unit_instance_id,
        attack_pools=(attack_pool,),
    )
    state.shooting_phase_state = ShootingPhaseState(
        battle_round=state.battle_round,
        active_player_id="player-a",
        selected_unit_ids=(attacker.unit_instance_id,),
        shot_unit_ids=(attacker.unit_instance_id,),
        attack_pools=(attack_pool,),
        attack_sequence=attack_sequence,
    )
    decisions = DecisionController()
    manager = DiceRollManager(state.game_id, event_log=decisions.event_log)
    wound_roll_state = manager.roll_fixed(
        attack_sequence_wound_roll_spec(
            weapon_profile_id=weapon_profile.profile_id,
            attack_context_id=attack_sequence.attack_context_id(),
            attacker_player_id="player-a",
        ),
        [1],
    )
    permission = RerollPermission(
        source_id=SOURCE_RULE_ID,
        timing_window="attack_sequence.wound",
        owning_player_id="player-a",
        eligible_roll_type="attack_sequence.wound",
        component_selection_policy=RerollComponentSelectionPolicy.WHOLE_ROLL,
    )
    source_payload = validate_json_value(
        {
            "effect_kind": "drukhari_test_source_backed_wound_reroll",
            "target_unit_instance_id": defender.unit_instance_id,
        }
    )
    state.record_persisting_effect(
        _persisting_effect(
            effect_id="drukhari-test:source-drift-effect",
            unit_instance_id=attacker.unit_instance_id,
            owner_player_id="player-a",
            effect_payload=source_backed_reroll_permission_effect_payload(
                target_unit_instance_ids=(attacker.unit_instance_id,),
                permission=permission,
                source_payload=source_payload,
            ),
        )
    )
    request = manager.build_reroll_request(
        wound_roll_state,
        request_id="drukhari-test:source-drift-reroll-request",
        actor_id="player-a",
        permission=permission,
        extra_payload={
            "source_rule_id": SOURCE_RULE_ID,
            "attack_context": {
                "game_id": state.game_id,
                "battle_round": state.battle_round,
                "phase": BattlePhase.SHOOTING.value,
                "unit_instance_id": attacker.unit_instance_id,
                "attack_context_id": attack_sequence.attack_context_id(),
                "weapon_profile_id": weapon_profile.profile_id,
                "target_unit_instance_id": defender.unit_instance_id,
                "wound_roll_state": validate_json_value(wound_roll_state.to_payload()),
                "source_payload": source_payload,
            },
        },
    )
    decisions.request_decision(request)
    result = DecisionResult.for_request(
        result_id="drukhari-test:source-drift-reroll-result",
        request=request,
        selected_option_id="reroll:0",
    )
    decisions.submit_result(result)
    state.persisting_effects.clear()

    with pytest.raises(GameLifecycleError, match="source context drift"):
        _shooting_phase_handler(ShootingUnitSelectedGrantRegistry.empty()).apply_decision(
            state=state,
            result=result,
            decisions=decisions,
        )


def test_hatred_eternal_selected_to_fight_grant_spends_pain_token_and_unlocks_hit_reroll() -> None:
    lifecycle, units = _fight_lifecycle(
        alpha_unit_ids=("attacker",),
        enemy_unit_ids=("enemy",),
        origins={
            "attacker": Pose.at(10.0, 20.0),
            "enemy": Pose.at(12.0, 20.0),
        },
        game_id="drukhari-test-hatred-fight-grant",
        datasheet_id="core-character-leader",
        model_profile_id="core-character-leader",
        model_count=1,
    )
    state = _lifecycle_state(lifecycle)
    _mark_player_as_drukhari(
        state,
        player_id="player-a",
        datasheet_abilities=(_hatred_eternal_ability(),),
    )
    unit = units["attacker"]
    state.gain_faction_resource(
        player_id="player-a",
        resource_kind=PAIN_TOKEN_RESOURCE_KIND,
        amount=1,
        source_id="drukhari-test:hatred-fight-token",
    )
    _refresh_lifecycle_runtime_content(lifecycle)

    activation_request = _advance_to_fight_order_request(lifecycle)
    grant_request = _decision_request_from_status(
        lifecycle.submit_decision(
            DecisionResult.for_request(
                result_id="drukhari-test:hatred-fight-select",
                request=activation_request,
                selected_option_id=fight_activation_option_id(
                    unit_instance_id=unit.unit_instance_id,
                    fight_type=RulesetDescriptor.warhammer_40000_eleventh().fight_policy.fight_types[
                        0
                    ],
                ),
            )
        )
    )
    assert grant_request.decision_type == SELECT_FIGHT_UNIT_GRANT_DECISION_TYPE
    assert grant_request.option_by_id(army_rule.HATRED_ETERNAL_FIGHT_HOOK_ID).option_id == (
        army_rule.HATRED_ETERNAL_FIGHT_HOOK_ID
    )

    melee_request = _decision_request_from_status(
        lifecycle.submit_decision(
            DecisionResult.for_request(
                result_id="drukhari-test:hatred-fight-grant",
                request=grant_request,
                selected_option_id=army_rule.HATRED_ETERNAL_FIGHT_HOOK_ID,
            )
        )
    )

    assert melee_request.decision_type == SUBMIT_MELEE_DECLARATION_DECISION_TYPE
    assert pain_tokens_available(state, player_id="player-a") == 0
    permission = source_backed_reroll_permission_for_unit(
        state=state,
        player_id="player-a",
        unit_instance_id=unit.unit_instance_id,
        roll_type="attack_sequence.hit",
        timing_window="attack_sequence.hit",
    )
    assert permission is not None
    assert permission.source_id.startswith(SOURCE_RULE_ID)
    grant_payload = _event_payloads(lifecycle, "fight_unit_selected_grant_decision_resolved")[0]
    selected_grants = cast(list[dict[str, object]], grant_payload["selected_fight_unit_grants"])
    source_payload = source_payload_from_reroll_effect_payload(
        cast(
            dict[str, JsonValue],
            cast(list[dict[str, object]], grant_payload["persisting_effects"])[1]["effect_payload"],
        )
    )
    assert selected_grants[0]["hook_id"] == army_rule.HATRED_ETERNAL_FIGHT_HOOK_ID
    assert source_payload["trigger"] == "selected_to_fight"
    assert source_payload["phase"] == BattlePhaseKind.FIGHT.value


def test_hatred_eternal_accepted_fight_hit_reroll_resumes_attack_sequence() -> None:
    lifecycle, units = _fight_lifecycle(
        alpha_unit_ids=("attacker",),
        enemy_unit_ids=("enemy",),
        origins={
            "attacker": Pose.at(10.0, 20.0),
            "enemy": Pose.at(12.0, 20.0),
        },
        game_id="drukhari-test-hatred-fight-consumer",
        datasheet_id="core-character-leader",
        model_profile_id="core-character-leader",
        model_count=1,
    )
    state = _lifecycle_state(lifecycle)
    _mark_player_as_drukhari(
        state,
        player_id="player-a",
        datasheet_abilities=(_hatred_eternal_ability(),),
    )
    unit = units["attacker"]
    state.gain_faction_resource(
        player_id="player-a",
        resource_kind=PAIN_TOKEN_RESOURCE_KIND,
        amount=1,
        source_id="drukhari-test:hatred-fight-consumer-token",
    )
    _refresh_lifecycle_runtime_content(lifecycle)

    activation_request = _advance_to_fight_order_request(lifecycle)
    grant_request = _decision_request_from_status(
        lifecycle.submit_decision(
            DecisionResult.for_request(
                result_id="drukhari-test:hatred-fight-consumer-select",
                request=activation_request,
                selected_option_id=fight_activation_option_id(
                    unit_instance_id=unit.unit_instance_id,
                    fight_type=RulesetDescriptor.warhammer_40000_eleventh().fight_policy.fight_types[
                        0
                    ],
                ),
            )
        )
    )
    melee_request = _decision_request_from_status(
        lifecycle.submit_decision(
            DecisionResult.for_request(
                result_id="drukhari-test:hatred-fight-consumer-grant",
                request=grant_request,
                selected_option_id=army_rule.HATRED_ETERNAL_FIGHT_HOOK_ID,
            )
        )
    )
    proposal_request = MeleeDeclarationProposalRequest.from_decision_request(melee_request)
    weapon_payload = _first_primary_melee_weapon_payload(proposal_request)
    weapon_profile_id = cast(str, weapon_payload["weapon_profile_id"])
    declaration_result_id = "drukhari-test:hatred-fight-consumer-declaration"
    sequence_id = (
        f"melee-sequence:{state.game_id}:round-{state.battle_round:02d}:"
        f"{unit.unit_instance_id}:{declaration_result_id}"
    )
    attack_context_id = f"{sequence_id}:pool-001:attack-001"
    fixed_rolls = DiceRollManager(state.game_id, event_log=lifecycle.decision_controller.event_log)
    fixed_rolls.roll_fixed(
        attack_sequence_hit_roll_spec(
            weapon_profile_id=weapon_profile_id,
            attack_context_id=attack_context_id,
            attacker_player_id="player-a",
        ),
        [1],
    )
    fixed_rolls.roll_fixed(
        attack_sequence_wound_roll_spec(
            weapon_profile_id=weapon_profile_id,
            attack_context_id=attack_context_id,
            attacker_player_id="player-a",
        ),
        [6],
    )

    reroll_request = _decision_request_from_status(
        _submit_minimal_melee_declaration(
            lifecycle,
            request=melee_request,
            result_id=declaration_result_id,
        )
    )
    assert reroll_request.decision_type == DICE_REROLL_DECISION_TYPE
    reroll_request_payload = cast(dict[str, object], reroll_request.payload)
    attack_context_payload = cast(dict[str, object], reroll_request_payload["attack_context"])
    assert attack_context_payload["phase"] == BattlePhase.FIGHT.value
    initial_hit_state = DiceRollState.from_payload(
        cast(DiceRollStatePayload, attack_context_payload["hit_roll_state"])
    )
    assert initial_hit_state.current_total == 1

    accepted_status = lifecycle.submit_decision(
        DecisionResult.for_request(
            result_id="drukhari-test:hatred-fight-consumer-accept-reroll",
            request=reroll_request,
            selected_option_id="reroll:0",
        )
    )

    assert accepted_status.status_kind is not LifecycleStatusKind.INVALID
    reroll_payloads = _event_payloads(lifecycle, "dice_reroll_resolved")
    assert len(reroll_payloads) == 1
    rerolled_state = DiceRollState.from_payload(cast(DiceRollStatePayload, reroll_payloads[0]))
    assert rerolled_state.original_result.roll_id == initial_hit_state.original_result.roll_id
    hit_payload = _attack_step_payload(
        _event_payloads(lifecycle, "attack_sequence_step"),
        AttackSequenceStep.HIT,
    )
    resolved_hit = cast(dict[str, object], hit_payload["payload"])
    assert resolved_hit["successful"] is True
    assert resolved_hit["unmodified_roll"] == rerolled_state.current_total
    assert cast(dict[str, object], resolved_hit["roll_state"]) == rerolled_state.to_payload()
    wound_payload = _attack_step_payload(
        _event_payloads(lifecycle, "attack_sequence_step"),
        AttackSequenceStep.WOUND,
    )
    resolved_wound = cast(dict[str, object], wound_payload["payload"])
    assert resolved_wound["successful"] is True


def test_hatred_eternal_hit_reroll_request_ignores_ineligible_contexts() -> None:
    state = _battle_state()
    _set_current_battle_phase(state, BattlePhase.SHOOTING)
    unit = _unit_for_player(state, player_id="player-a")
    decisions = DecisionController()
    manager = DiceRollManager(state.game_id, event_log=decisions.event_log)
    roll_state = manager.roll_fixed(
        attack_sequence_hit_roll_spec(
            weapon_profile_id="drukhari-test-splinter-rifle",
            attack_context_id="drukhari-test:ineligible-attack-context",
            attacker_player_id="player-a",
        ),
        [2],
    )

    assert (
        _request_source_backed_hit_reroll_if_available(
            state=state,
            decisions=decisions,
            roll_state=None,
            attacking_unit_instance_id=unit.unit_instance_id,
            attack_context_id="drukhari-test:ineligible-attack-context",
            source_phase=BattlePhase.SHOOTING,
            weapon_profile_id="drukhari-test-splinter-rifle",
        )
        is None
    )
    assert (
        _request_source_backed_hit_reroll_if_available(
            state=state,
            decisions=decisions,
            roll_state=roll_state,
            attacking_unit_instance_id=unit.unit_instance_id,
            attack_context_id="drukhari-test:ineligible-attack-context",
            source_phase=BattlePhase.FIGHT,
            weapon_profile_id="drukhari-test-splinter-rifle",
        )
        is None
    )
    assert (
        _request_source_backed_hit_reroll_if_available(
            state=state,
            decisions=decisions,
            roll_state=roll_state,
            attacking_unit_instance_id=unit.unit_instance_id,
            attack_context_id="drukhari-test:ineligible-attack-context",
            source_phase=BattlePhase.SHOOTING,
            weapon_profile_id="drukhari-test-splinter-rifle",
        )
        is None
    )

    forbidden_spec = replace(
        roll_state.original_result.spec,
        reroll_forbidden_rule_ids=("drukhari-test:forbidden-hit-reroll",),
    )
    forbidden_state = replace(
        roll_state,
        original_result=replace(roll_state.original_result, spec=forbidden_spec),
    )
    assert (
        _request_source_backed_hit_reroll_if_available(
            state=state,
            decisions=decisions,
            roll_state=forbidden_state,
            attacking_unit_instance_id=unit.unit_instance_id,
            attack_context_id="drukhari-test:ineligible-attack-context",
            source_phase=BattlePhase.SHOOTING,
            weapon_profile_id="drukhari-test-splinter-rifle",
        )
        is None
    )

    no_actor_spec = replace(roll_state.original_result.spec, actor_id=None)
    no_actor_state = replace(
        roll_state,
        original_result=replace(roll_state.original_result, spec=no_actor_spec),
    )
    assert (
        _request_source_backed_hit_reroll_if_available(
            state=state,
            decisions=decisions,
            roll_state=no_actor_state,
            attacking_unit_instance_id=unit.unit_instance_id,
            attack_context_id="drukhari-test:ineligible-attack-context",
            source_phase=BattlePhase.SHOOTING,
            weapon_profile_id="drukhari-test-splinter-rifle",
        )
        is None
    )


def test_source_backed_hit_reroll_replay_guard_is_fail_fast_for_malformed_payload() -> None:
    decisions = DecisionController()
    malformed_request = DecisionRequest(
        request_id="drukhari-test:malformed-reroll-request",
        decision_type=DICE_REROLL_DECISION_TYPE,
        actor_id="player-a",
        payload=None,
        options=(
            DecisionOption(
                option_id="decline",
                label="Decline",
                payload={"submission_kind": "decline"},
            ),
        ),
    )
    decisions.request_decision(malformed_request)
    decisions.submit_result(
        DecisionResult.for_request(
            result_id="drukhari-test:malformed-reroll-result",
            request=malformed_request,
            selected_option_id="decline",
        )
    )

    with pytest.raises(GameLifecycleError, match="payload must be an object"):
        _source_backed_reroll_already_answered(
            decisions=decisions,
            roll_id="drukhari-test:roll",
            source_id=SOURCE_RULE_ID,
        )

    decisions = DecisionController()
    non_matching_request = DecisionRequest(
        request_id="drukhari-test:non-matching-reroll-request",
        decision_type=DICE_REROLL_DECISION_TYPE,
        actor_id="player-a",
        payload={
            "roll_id": "drukhari-test:roll",
            "permission": None,
        },
        options=(
            DecisionOption(
                option_id="decline",
                label="Decline",
                payload={"submission_kind": "decline"},
            ),
        ),
    )
    decisions.request_decision(non_matching_request)
    decisions.submit_result(
        DecisionResult.for_request(
            result_id="drukhari-test:non-matching-reroll-result",
            request=non_matching_request,
            selected_option_id="decline",
        )
    )

    assert not _source_backed_reroll_already_answered(
        decisions=decisions,
        roll_id="drukhari-test:roll",
        source_id=SOURCE_RULE_ID,
    )


def test_drukhari_advance_roll_permission_requires_lithe_agility_empowerment() -> None:
    state = _battle_state()
    _mark_player_as_drukhari(
        state,
        player_id="player-a",
        datasheet_abilities=(_lithe_agility_ability(),),
    )
    unit = _unit_for_player(state, player_id="player-a")
    state.gain_faction_resource(
        player_id="player-a",
        resource_kind=PAIN_TOKEN_RESOURCE_KIND,
        amount=1,
        source_id="drukhari-test:advance-token",
    )

    assert (
        _advance_reroll_permission_for_unit(
            state=state,
            unit=unit,
            unit_instance_id=unit.unit_instance_id,
            player_id="player-a",
            keywords=unit.keywords,
            ability_index=AbilityCatalogIndex.from_records(()),
            current_model_instance_ids=tuple(
                sorted(model.model_instance_id for model in unit.own_models)
            ),
        )
        is None
    )

    state.record_persisting_effect(
        PersistingEffect(
            effect_id="drukhari-test:lithe-advance-empowered",
            source_rule_id=SOURCE_RULE_ID,
            owner_player_id="player-a",
            target_unit_instance_ids=(unit.unit_instance_id,),
            started_battle_round=state.battle_round,
            started_phase=BattlePhaseKind.MOVEMENT,
            expiration=EffectExpiration.end_phase(
                battle_round=state.battle_round,
                phase=BattlePhaseKind.MOVEMENT,
                player_id="player-a",
            ),
            effect_payload=power_from_pain_reroll_permission_effect_payload(
                unit_instance_id=unit.unit_instance_id,
                target_unit_instance_ids=(unit.unit_instance_id,),
                trigger="advance",
                phase=BattlePhaseKind.MOVEMENT,
                pain_ability_keys=(LITHE_AGILITY_ABILITY_KEY,),
                permission=lithe_agility_advance_reroll_permission(
                    state=state,
                    player_id="player-a",
                    unit_instance_id=unit.unit_instance_id,
                ),
                source_context={"test_context": "advance_permission"},
            ),
        )
    )
    permission = _advance_reroll_permission_for_unit(
        state=state,
        unit=unit,
        unit_instance_id=unit.unit_instance_id,
        player_id="player-a",
        keywords=unit.keywords,
        ability_index=AbilityCatalogIndex.from_records(()),
        current_model_instance_ids=tuple(
            sorted(model.model_instance_id for model in unit.own_models)
        ),
    )

    assert permission is not None
    assert permission.source_id.startswith(SOURCE_RULE_ID)


def test_lithe_agility_advance_grant_requires_drukhari_rules_unit() -> None:
    state = _battle_state()
    _set_current_battle_phase(state, BattlePhase.MOVEMENT)
    _mark_player_as_drukhari(
        state,
        player_id="player-a",
        datasheet_abilities=(_lithe_agility_ability(),),
        faction_keywords=("HARLEQUINS",),
    )
    unit = _unit_for_player(state, player_id="player-a")
    state.gain_faction_resource(
        player_id="player-a",
        resource_kind=PAIN_TOKEN_RESOURCE_KIND,
        amount=1,
        source_id="drukhari-test:lithe-non-drukhari-token",
    )

    grant = army_rule.lithe_agility_advance_grant(
        AdvanceMoveContext(
            state=state,
            player_id="player-a",
            battle_round=state.battle_round,
            unit_instance_id=unit.unit_instance_id,
            movement_phase_action="advance",
            movement_request_id="drukhari-test:non-drukhari-advance-request",
            movement_result_id="drukhari-test:non-drukhari-advance-result",
        )
    )

    assert grant is None


def test_faction_resource_ledger_validates_transactions_and_effect_payloads() -> None:
    ledgers = initial_faction_resource_ledgers(("player-a", "player-b"))
    assert [ledger.player_id for ledger in ledgers] == ["player-a", "player-b"]

    ledger = FactionResourceLedger.empty_for_player("player-a")
    ledger, gain = ledger.gain(
        battle_round=1,
        resource_kind=PAIN_TOKEN_RESOURCE_KIND,
        amount=2,
        source_id="drukhari-test:resource-gain",
    )
    assert gain.status is FactionResourceStatus.APPLIED
    assert ledger.total(PAIN_TOKEN_RESOURCE_KIND) == 2

    same_ledger, insufficient = ledger.spend(
        battle_round=1,
        resource_kind=PAIN_TOKEN_RESOURCE_KIND,
        amount=3,
        source_id="drukhari-test:resource-insufficient",
    )
    assert same_ledger is ledger
    assert insufficient.status is FactionResourceStatus.INSUFFICIENT

    ledger, spend = ledger.spend(
        battle_round=1,
        resource_kind=PAIN_TOKEN_RESOURCE_KIND,
        amount=1,
        source_id="drukhari-test:resource-spend",
    )
    assert spend.status is FactionResourceStatus.APPLIED
    assert ledger.total(PAIN_TOKEN_RESOURCE_KIND) == 1
    assert FactionResourceLedger.from_payload(ledger.to_payload()) == ledger
    assert spend.transaction is not None
    assert (
        FactionResourceTransaction.from_payload(spend.transaction.to_payload()) == spend.transaction
    )
    assert (
        faction_resource_transaction_kind_from_token(FactionResourceTransactionKind.GAIN)
        is FactionResourceTransactionKind.GAIN
    )
    assert (
        faction_resource_status_from_token(FactionResourceStatus.APPLIED)
        is FactionResourceStatus.APPLIED
    )

    state = _battle_state()
    state.gain_faction_resource(
        player_id="player-a",
        resource_kind=PAIN_TOKEN_RESOURCE_KIND,
        amount=1,
        source_id="drukhari-test:state-resource-gain",
    )
    spend_effect = faction_resource_spend_effect_payload(
        resource_kind=PAIN_TOKEN_RESOURCE_KIND,
        amount=1,
        reason="drukhari-test-resource-spend",
    )
    assert (
        apply_faction_resource_spend_effect(
            state=state,
            player_id="player-a",
            source_id="drukhari-test:state-resource-spend",
            effect_payload=[],
        )
        is None
    )
    assert (
        apply_faction_resource_spend_effect(
            state=state,
            player_id="player-a",
            source_id="drukhari-test:state-resource-spend",
            effect_payload={"effect_kind": "different_effect"},
        )
        is None
    )
    applied = apply_faction_resource_spend_effect(
        state=state,
        player_id="player-a",
        source_id="drukhari-test:state-resource-spend",
        effect_payload=spend_effect,
    )
    assert applied is not None
    enriched = faction_resource_result_enriched_payload(
        effect_payload=spend_effect,
        result=applied,
    )
    assert cast(dict[str, JsonValue], enriched)["faction_resource_result"] == applied.to_payload()
    assert (
        faction_resource_result_enriched_payload(
            effect_payload=spend_effect,
            result=None,
        )
        == spend_effect
    )
    assert (
        FactionResourceLedger(
            player_id="player-a",
            resources=cast(dict[str, int], None),
        ).resources
        == {}
    )

    invalid_transaction = FactionResourceTransaction(
        transaction_id="drukhari-test:transaction",
        player_id="player-a",
        battle_round=1,
        resource_kind=PAIN_TOKEN_RESOURCE_KIND,
        transaction_kind=FactionResourceTransactionKind.GAIN,
        amount=1,
        source_id="drukhari-test:transaction-source",
    )

    invalid_cases: tuple[Callable[[], object], ...] = (
        lambda: faction_resource_transaction_kind_from_token(1),
        lambda: faction_resource_transaction_kind_from_token("unsupported"),
        lambda: faction_resource_status_from_token(1),
        lambda: faction_resource_status_from_token("unsupported"),
        lambda: FactionResourceResult(
            player_id="player-a",
            battle_round=1,
            resource_kind=PAIN_TOKEN_RESOURCE_KIND,
            transaction_kind=FactionResourceTransactionKind.GAIN,
            requested_amount=2,
            applied_amount=1,
            status=FactionResourceStatus.APPLIED,
            source_id="drukhari-test:applied-drift",
            transaction=invalid_transaction,
        ),
        lambda: FactionResourceResult(
            player_id="player-a",
            battle_round=1,
            resource_kind=PAIN_TOKEN_RESOURCE_KIND,
            transaction_kind=FactionResourceTransactionKind.GAIN,
            requested_amount=1,
            applied_amount=1,
            status=FactionResourceStatus.APPLIED,
            source_id="drukhari-test:missing-transaction",
        ),
        lambda: FactionResourceResult(
            player_id="player-a",
            battle_round=1,
            resource_kind=PAIN_TOKEN_RESOURCE_KIND,
            transaction_kind=FactionResourceTransactionKind.GAIN,
            requested_amount=1,
            applied_amount=1,
            status=FactionResourceStatus.APPLIED,
            source_id="drukhari-test:bad-transaction",
            transaction=cast(FactionResourceTransaction, object()),
        ),
        lambda: FactionResourceResult(
            player_id="player-a",
            battle_round=1,
            resource_kind=PAIN_TOKEN_RESOURCE_KIND,
            transaction_kind=FactionResourceTransactionKind.GAIN,
            requested_amount=1,
            applied_amount=1,
            status=FactionResourceStatus.APPLIED,
            source_id="drukhari-test:applied-with-reason",
            transaction=invalid_transaction,
            insufficient_reason="should-not-exist",
        ),
        lambda: FactionResourceResult(
            player_id="player-a",
            battle_round=1,
            resource_kind=PAIN_TOKEN_RESOURCE_KIND,
            transaction_kind=FactionResourceTransactionKind.SPEND,
            requested_amount=1,
            applied_amount=1,
            status=FactionResourceStatus.INSUFFICIENT,
            source_id="drukhari-test:insufficient-applied",
            insufficient_reason="insufficient_resource",
        ),
        lambda: FactionResourceResult(
            player_id="player-a",
            battle_round=1,
            resource_kind=PAIN_TOKEN_RESOURCE_KIND,
            transaction_kind=FactionResourceTransactionKind.SPEND,
            requested_amount=1,
            applied_amount=0,
            status=FactionResourceStatus.INSUFFICIENT,
            source_id="drukhari-test:insufficient-transaction",
            transaction=invalid_transaction,
            insufficient_reason="insufficient_resource",
        ),
        lambda: FactionResourceResult(
            player_id="player-a",
            battle_round=1,
            resource_kind=PAIN_TOKEN_RESOURCE_KIND,
            transaction_kind=FactionResourceTransactionKind.SPEND,
            requested_amount=1,
            applied_amount=0,
            status=FactionResourceStatus.INSUFFICIENT,
            source_id="drukhari-test:insufficient-no-reason",
        ),
        lambda: FactionResourceLedger(
            player_id="player-a",
            resources=cast(dict[str, int], []),
        ),
        lambda: FactionResourceLedger(
            player_id="player-a",
            resources=cast(dict[str, int], {1: 1}),
        ),
        lambda: FactionResourceLedger(
            player_id="player-a",
            resources={" ": 1},
        ),
        lambda: FactionResourceLedger(
            player_id="player-a",
            resources={" pain ": 1, "pain": 2},
        ),
        lambda: FactionResourceLedger(
            player_id="player-a",
            resources={"pain": -1},
        ),
        lambda: FactionResourceLedger(
            player_id="player-a",
            resources=cast(dict[str, int], {"pain": "one"}),
        ),
        lambda: FactionResourceTransaction(
            transaction_id="drukhari-test:bad-amount-type",
            player_id="player-a",
            battle_round=1,
            resource_kind=PAIN_TOKEN_RESOURCE_KIND,
            transaction_kind=FactionResourceTransactionKind.GAIN,
            amount=cast(int, "one"),
            source_id="drukhari-test:bad-amount-type-source",
        ),
        lambda: FactionResourceLedger(
            player_id="player-a",
            transactions=cast(tuple[FactionResourceTransaction, ...], []),
        ),
        lambda: FactionResourceLedger(
            player_id="player-a",
            transactions=cast(tuple[FactionResourceTransaction, ...], ("bad",)),
        ),
        lambda: FactionResourceLedger(
            player_id="player-b",
            transactions=(invalid_transaction,),
        ),
        lambda: FactionResourceLedger(
            player_id="player-a",
            transactions=(invalid_transaction, invalid_transaction),
        ),
        lambda: faction_resource_spend_effect_payload(
            resource_kind=PAIN_TOKEN_RESOURCE_KIND,
            amount=0,
            reason="drukhari-test-invalid-amount",
        ),
        lambda: apply_faction_resource_spend_effect(
            state=object(),
            player_id="player-a",
            source_id="drukhari-test:wrong-state",
            effect_payload=spend_effect,
        ),
        lambda: apply_faction_resource_spend_effect(
            state=_battle_state(),
            player_id="player-a",
            source_id="drukhari-test:no-token",
            effect_payload=spend_effect,
        ),
        lambda: apply_faction_resource_spend_effect(
            state=_battle_state(),
            player_id="player-a",
            source_id="drukhari-test:bad-amount",
            effect_payload={
                "effect_kind": FACTION_RESOURCE_SPEND_EFFECT_KIND,
                "resource_kind": PAIN_TOKEN_RESOURCE_KIND,
                "amount": "one",
                "reason": "drukhari-test",
            },
        ),
        lambda: faction_resource_result_enriched_payload(
            effect_payload=[],
            result=applied,
        ),
    )
    for invalid_case in invalid_cases:
        with pytest.raises(GameLifecycleError):
            invalid_case()


def test_generic_command_and_unit_destroyed_hooks_validate_contexts_and_registries() -> None:
    state = _battle_state()
    decisions = DecisionController()
    command_calls: list[str] = []
    command_context = CommandPhaseStartContext(
        state=state,
        decisions=decisions,
        active_player_id="player-a",
    )
    command_binding = CommandPhaseStartHookBinding(
        hook_id="drukhari-test:command-hook",
        source_id="drukhari-test:command-source",
        handler=lambda context: command_calls.append(context.active_player_id),
    )
    command_registry = CommandPhaseStartHookRegistry.from_bindings((command_binding,))

    assert command_registry.all_bindings() == (command_binding,)
    command_registry.resolve(command_context)
    assert command_calls == ["player-a"]
    assert CommandPhaseStartHookRegistry.empty().all_bindings() == ()

    command_invalid_cases: tuple[Callable[[], object], ...] = (
        lambda: CommandPhaseStartContext(
            state=cast(GameState, object()),
            decisions=decisions,
            active_player_id="player-a",
        ),
        lambda: CommandPhaseStartContext(
            state=state,
            decisions=cast(DecisionController, object()),
            active_player_id="player-a",
        ),
        lambda: CommandPhaseStartContext(
            state=state,
            decisions=decisions,
            active_player_id="player-b",
        ),
        lambda: CommandPhaseStartHookBinding(
            hook_id=cast(str, 1),
            source_id="drukhari-test:command-source",
            handler=lambda context: command_calls.append(context.active_player_id),
        ),
        lambda: CommandPhaseStartHookBinding(
            hook_id=" ",
            source_id="drukhari-test:command-source",
            handler=lambda context: command_calls.append(context.active_player_id),
        ),
        lambda: CommandPhaseStartHookBinding(
            hook_id="drukhari-test:bad-handler",
            source_id="drukhari-test:command-source",
            handler=cast(CommandPhaseStartHandler, object()),
        ),
        lambda: CommandPhaseStartHookRegistry(
            bindings=cast(tuple[CommandPhaseStartHookBinding, ...], []),
        ),
        lambda: CommandPhaseStartHookRegistry(
            bindings=cast(tuple[CommandPhaseStartHookBinding, ...], ("bad",)),
        ),
        lambda: CommandPhaseStartHookRegistry.from_bindings((command_binding, command_binding)),
        lambda: command_registry.resolve(cast(CommandPhaseStartContext, object())),
    )
    for command_invalid_case in command_invalid_cases:
        with pytest.raises(GameLifecycleError):
            command_invalid_case()

    _set_current_battle_phase(state, BattlePhase.MOVEMENT)
    with pytest.raises(GameLifecycleError):
        CommandPhaseStartContext(
            state=state,
            decisions=decisions,
            active_player_id="player-a",
        )
    _set_current_battle_phase(state, BattlePhase.COMMAND)

    target_unit = _unit_for_player(state, player_id="player-b")
    destroyed_event = decisions.event_log.append(
        "model_destroyed",
        {
            "game_id": state.game_id,
            "battle_round": state.battle_round,
            "active_player_id": state.active_player_id,
            "phase": BattlePhase.SHOOTING.value,
            "destroying_player_id": "player-a",
            "target_unit_instance_id": target_unit.unit_instance_id,
            "model_instance_id": target_unit.own_models[-1].model_instance_id,
        },
    )
    unit_destroyed_calls: list[str] = []
    unit_destroyed_context = UnitDestroyedContext(
        state=state,
        decisions=decisions,
        completed_phase=cast(BattlePhase, BattlePhase.SHOOTING.value),
        model_destroyed_event_id=destroyed_event.event_id,
        model_destroyed_payload=cast(dict[str, JsonValue], destroyed_event.payload),
        destroying_player_id="player-a",
        destroyed_unit_instance_id=target_unit.unit_instance_id,
        destroyed_player_id="player-b",
    )
    unit_binding = UnitDestroyedHookBinding(
        hook_id="drukhari-test:unit-destroyed-hook",
        source_id="drukhari-test:unit-destroyed-source",
        handler=lambda context: unit_destroyed_calls.append(context.destroyed_player_id),
    )
    unit_registry = UnitDestroyedHookRegistry.from_bindings((unit_binding,))

    assert unit_destroyed_context.completed_phase is BattlePhase.SHOOTING
    unit_registry.resolve(unit_destroyed_context)
    assert unit_destroyed_calls == ["player-b"]
    assert UnitDestroyedHookRegistry.empty().all_bindings() == ()

    unit_invalid_cases: tuple[Callable[[], object], ...] = (
        lambda: UnitDestroyedContext(
            state=cast(GameState, object()),
            decisions=decisions,
            completed_phase=BattlePhase.SHOOTING,
            model_destroyed_event_id=destroyed_event.event_id,
            model_destroyed_payload=cast(dict[str, JsonValue], destroyed_event.payload),
            destroying_player_id="player-a",
            destroyed_unit_instance_id=target_unit.unit_instance_id,
            destroyed_player_id="player-b",
        ),
        lambda: UnitDestroyedContext(
            state=state,
            decisions=cast(DecisionController, object()),
            completed_phase=BattlePhase.SHOOTING,
            model_destroyed_event_id=destroyed_event.event_id,
            model_destroyed_payload=cast(dict[str, JsonValue], destroyed_event.payload),
            destroying_player_id="player-a",
            destroyed_unit_instance_id=target_unit.unit_instance_id,
            destroyed_player_id="player-b",
        ),
        lambda: UnitDestroyedContext(
            state=state,
            decisions=decisions,
            completed_phase=cast(BattlePhase, []),
            model_destroyed_event_id=destroyed_event.event_id,
            model_destroyed_payload=cast(dict[str, JsonValue], destroyed_event.payload),
            destroying_player_id="player-a",
            destroyed_unit_instance_id=target_unit.unit_instance_id,
            destroyed_player_id="player-b",
        ),
        lambda: UnitDestroyedContext(
            state=state,
            decisions=decisions,
            completed_phase=cast(BattlePhase, "unsupported"),
            model_destroyed_event_id=destroyed_event.event_id,
            model_destroyed_payload=cast(dict[str, JsonValue], destroyed_event.payload),
            destroying_player_id="player-a",
            destroyed_unit_instance_id=target_unit.unit_instance_id,
            destroyed_player_id="player-b",
        ),
        lambda: UnitDestroyedContext(
            state=state,
            decisions=decisions,
            completed_phase=BattlePhase.SHOOTING,
            model_destroyed_event_id=destroyed_event.event_id,
            model_destroyed_payload=cast(dict[str, JsonValue], []),
            destroying_player_id="player-a",
            destroyed_unit_instance_id=target_unit.unit_instance_id,
            destroyed_player_id="player-b",
        ),
        lambda: UnitDestroyedContext(
            state=state,
            decisions=decisions,
            completed_phase=BattlePhase.SHOOTING,
            model_destroyed_event_id=destroyed_event.event_id,
            model_destroyed_payload=cast(dict[str, JsonValue], destroyed_event.payload),
            destroying_player_id="player-a",
            destroyed_unit_instance_id=target_unit.unit_instance_id,
            destroyed_player_id="player-a",
        ),
        lambda: UnitDestroyedHookBinding(
            hook_id=cast(str, 1),
            source_id="drukhari-test:unit-source",
            handler=lambda context: unit_destroyed_calls.append(context.destroyed_player_id),
        ),
        lambda: UnitDestroyedHookBinding(
            hook_id=" ",
            source_id="drukhari-test:unit-source",
            handler=lambda context: unit_destroyed_calls.append(context.destroyed_player_id),
        ),
        lambda: UnitDestroyedHookBinding(
            hook_id="drukhari-test:bad-unit-handler",
            source_id="drukhari-test:unit-source",
            handler=cast(UnitDestroyedHandler, object()),
        ),
        lambda: UnitDestroyedHookRegistry(
            bindings=cast(tuple[UnitDestroyedHookBinding, ...], []),
        ),
        lambda: UnitDestroyedHookRegistry(
            bindings=cast(tuple[UnitDestroyedHookBinding, ...], ("bad",)),
        ),
        lambda: UnitDestroyedHookRegistry.from_bindings((unit_binding, unit_binding)),
        lambda: unit_registry.resolve(cast(UnitDestroyedContext, object())),
    )
    for unit_invalid_case in unit_invalid_cases:
        with pytest.raises(GameLifecycleError):
            unit_invalid_case()


def test_source_backed_reroll_payloads_and_lookup_are_fail_fast() -> None:
    state = _battle_state()
    unit = _unit_for_player(state, player_id="player-a")
    permission = lithe_agility_advance_reroll_permission(
        state=state,
        player_id="player-a",
        unit_instance_id=unit.unit_instance_id,
    )
    payload = source_backed_reroll_permission_effect_payload(
        target_unit_instance_ids=(unit.unit_instance_id,),
        permission=permission,
        source_payload={"effect_kind": "drukhari-test-source"},
    )

    assert source_payload_from_reroll_effect_payload(payload) == {
        "effect_kind": "drukhari-test-source"
    }
    state.record_persisting_effect(
        _persisting_effect(
            effect_id="drukhari-test:source-backed-other-owner",
            unit_instance_id=unit.unit_instance_id,
            owner_player_id="player-b",
            effect_payload=payload,
        )
    )
    state.record_persisting_effect(
        _persisting_effect(
            effect_id="drukhari-test:source-backed-non-object",
            unit_instance_id=unit.unit_instance_id,
            owner_player_id="player-a",
            effect_payload=[],
        )
    )
    wrong_timing_permission = RerollPermission(
        source_id="drukhari-test:wrong-timing-permission",
        timing_window="after_charge_roll",
        owning_player_id="player-a",
        eligible_roll_type="advance_roll",
        component_selection_policy=RerollComponentSelectionPolicy.WHOLE_ROLL,
    )
    state.record_persisting_effect(
        _persisting_effect(
            effect_id="drukhari-test:source-backed-wrong-timing",
            unit_instance_id=unit.unit_instance_id,
            owner_player_id="player-a",
            effect_payload=source_backed_reroll_permission_effect_payload(
                target_unit_instance_ids=(unit.unit_instance_id,),
                permission=wrong_timing_permission,
                source_payload={"effect_kind": "drukhari-test-source"},
            ),
        )
    )
    state.record_persisting_effect(
        _persisting_effect(
            effect_id="drukhari-test:source-backed-valid",
            unit_instance_id=unit.unit_instance_id,
            owner_player_id="player-a",
            effect_payload=payload,
        )
    )
    assert (
        source_backed_reroll_permission_for_unit(
            state=state,
            player_id="player-a",
            unit_instance_id=unit.unit_instance_id,
            roll_type="charge_roll",
            timing_window="after_advance_roll",
        )
        is None
    )
    assert (
        source_backed_reroll_permission_for_unit(
            state=state,
            player_id="player-a",
            unit_instance_id=unit.unit_instance_id,
            roll_type="advance_roll",
            timing_window="after_advance_roll",
        )
        == permission
    )

    invalid_payload_cases: tuple[Callable[[], object], ...] = (
        lambda: source_backed_reroll_permission_effect_payload(
            target_unit_instance_ids=(unit.unit_instance_id,),
            permission=cast(RerollPermission, object()),
            source_payload={},
        ),
        lambda: source_backed_reroll_permission_effect_payload(
            target_unit_instance_ids=cast(tuple[str, ...], []),
            permission=permission,
            source_payload={},
        ),
        lambda: source_backed_reroll_permission_effect_payload(
            target_unit_instance_ids=(),
            permission=permission,
            source_payload={},
        ),
        lambda: source_backed_reroll_permission_effect_payload(
            target_unit_instance_ids=(unit.unit_instance_id, unit.unit_instance_id),
            permission=permission,
            source_payload={},
        ),
        lambda: source_payload_from_reroll_effect_payload([]),
        lambda: source_payload_from_reroll_effect_payload({"effect_kind": "wrong"}),
        lambda: source_payload_from_reroll_effect_payload(
            {
                "effect_kind": SOURCE_BACKED_REROLL_PERMISSION_EFFECT_KIND,
                "source_payload": [],
            }
        ),
        lambda: source_backed_reroll_permission_for_unit(
            state=state,
            player_id=cast(str, 1),
            unit_instance_id=unit.unit_instance_id,
            roll_type="advance_roll",
            timing_window="after_advance_roll",
        ),
        lambda: source_backed_reroll_permission_for_unit(
            state=state,
            player_id=" ",
            unit_instance_id=unit.unit_instance_id,
            roll_type="advance_roll",
            timing_window="after_advance_roll",
        ),
        lambda: source_backed_reroll_permission_for_unit(
            state=object(),
            player_id="player-a",
            unit_instance_id=unit.unit_instance_id,
            roll_type="advance_roll",
            timing_window="after_advance_roll",
        ),
    )
    for invalid_case in invalid_payload_cases:
        with pytest.raises(GameLifecycleError):
            invalid_case()

    malformed_permission_state = _battle_state()
    malformed_permission_unit = _unit_for_player(malformed_permission_state, player_id="player-a")
    malformed_permission_state.record_persisting_effect(
        _persisting_effect(
            effect_id="drukhari-test:source-backed-missing-permission",
            unit_instance_id=malformed_permission_unit.unit_instance_id,
            owner_player_id="player-a",
            effect_payload={
                "effect_kind": SOURCE_BACKED_REROLL_PERMISSION_EFFECT_KIND,
                "source_payload": {"effect_kind": "drukhari-test-source"},
            },
        )
    )
    with pytest.raises(GameLifecycleError):
        source_backed_reroll_permission_for_unit(
            state=malformed_permission_state,
            player_id="player-a",
            unit_instance_id=malformed_permission_unit.unit_instance_id,
            roll_type="advance_roll",
            timing_window="after_advance_roll",
        )

    owner_drift_state = _battle_state()
    owner_drift_unit = _unit_for_player(owner_drift_state, player_id="player-a")
    owner_drift_permission = RerollPermission(
        source_id="drukhari-test:owner-drift-permission",
        timing_window="after_advance_roll",
        owning_player_id="player-b",
        eligible_roll_type="advance_roll",
        component_selection_policy=RerollComponentSelectionPolicy.WHOLE_ROLL,
    )
    owner_drift_state.record_persisting_effect(
        _persisting_effect(
            effect_id="drukhari-test:source-backed-owner-drift",
            unit_instance_id=owner_drift_unit.unit_instance_id,
            owner_player_id="player-a",
            effect_payload=source_backed_reroll_permission_effect_payload(
                target_unit_instance_ids=(owner_drift_unit.unit_instance_id,),
                permission=owner_drift_permission,
                source_payload={"effect_kind": "drukhari-test-source"},
            ),
        )
    )
    with pytest.raises(GameLifecycleError):
        source_backed_reroll_permission_for_unit(
            state=owner_drift_state,
            player_id="player-a",
            unit_instance_id=owner_drift_unit.unit_instance_id,
            roll_type="advance_roll",
            timing_window="after_advance_roll",
        )

    duplicate_state = _battle_state()
    duplicate_unit = _unit_for_player(duplicate_state, player_id="player-a")
    duplicate_payload = source_backed_reroll_permission_effect_payload(
        target_unit_instance_ids=(duplicate_unit.unit_instance_id,),
        permission=lithe_agility_charge_reroll_permission(
            state=duplicate_state,
            player_id="player-a",
            unit_instance_id=duplicate_unit.unit_instance_id,
        ),
        source_payload={"effect_kind": "drukhari-test-source"},
    )
    duplicate_state.record_persisting_effect(
        _persisting_effect(
            effect_id="drukhari-test:source-backed-duplicate-a",
            unit_instance_id=duplicate_unit.unit_instance_id,
            owner_player_id="player-a",
            effect_payload=duplicate_payload,
        )
    )
    duplicate_state.record_persisting_effect(
        _persisting_effect(
            effect_id="drukhari-test:source-backed-duplicate-b",
            unit_instance_id=duplicate_unit.unit_instance_id,
            owner_player_id="player-a",
            effect_payload=duplicate_payload,
        )
    )
    with pytest.raises(GameLifecycleError):
        source_backed_reroll_permission_for_unit(
            state=duplicate_state,
            player_id="player-a",
            unit_instance_id=duplicate_unit.unit_instance_id,
            roll_type="charge_roll",
            timing_window="after_charge_roll",
        )


def test_power_from_pain_helpers_validate_eligibility_and_payloads() -> None:
    state = _battle_state()
    unit = _unit_for_player(state, player_id="player-a")

    wrong_state_cases: tuple[Callable[[], object], ...] = (
        lambda: pain_tokens_available(object(), player_id="player-a"),
        lambda: spend_pain_token(object(), player_id="player-a", source_id="drukhari-test"),
        lambda: power_from_pain_target_unit_ids(object(), unit_instance_id=unit.unit_instance_id),
        lambda: drukhari_rules_unit_can_empower_for_ability(
            object(),
            player_id="player-a",
            unit_instance_id=unit.unit_instance_id,
            pain_ability_key=LITHE_AGILITY_ABILITY_KEY,
        ),
        lambda: pain_ability_keys_for_rules_unit(object(), unit_instance_id=unit.unit_instance_id),
        lambda: unit_is_empowered_through_pain_for_ability(
            object(),
            player_id="player-a",
            unit_instance_id=unit.unit_instance_id,
            pain_ability_key=LITHE_AGILITY_ABILITY_KEY,
        ),
        lambda: lithe_agility_advance_reroll_permission(
            state=object(),
            player_id="player-a",
            unit_instance_id=unit.unit_instance_id,
        ),
    )
    for wrong_state_case in wrong_state_cases:
        with pytest.raises(GameLifecycleError):
            wrong_state_case()

    with pytest.raises(GameLifecycleError):
        spend_pain_token(state, player_id="player-a", source_id="drukhari-test:no-token")
    with pytest.raises(GameLifecycleError):
        drukhari_rules_unit_can_empower_for_ability(
            state,
            player_id="missing-player",
            unit_instance_id=unit.unit_instance_id,
            pain_ability_key=LITHE_AGILITY_ABILITY_KEY,
        )

    _mark_player_as_drukhari(
        state,
        player_id="player-a",
        datasheet_abilities=(_lithe_agility_ability(), _hatred_eternal_ability()),
    )
    assert power_from_pain_target_unit_ids(state, unit_instance_id=unit.unit_instance_id) == (
        unit.unit_instance_id,
    )
    assert set(
        pain_ability_keys_for_rules_unit(
            state,
            unit_instance_id=unit.unit_instance_id,
        )
    ) == {LITHE_AGILITY_ABILITY_KEY, HATRED_ETERNAL_ABILITY_KEY}
    assert drukhari_rules_unit_can_empower_for_ability(
        state,
        player_id="player-a",
        unit_instance_id=unit.unit_instance_id,
        pain_ability_key=LITHE_AGILITY_ABILITY_KEY,
    )

    player_b_unit = _unit_for_player(state, player_id="player-b")
    with pytest.raises(GameLifecycleError):
        drukhari_rules_unit_can_empower_for_ability(
            state,
            player_id="player-a",
            unit_instance_id=player_b_unit.unit_instance_id,
            pain_ability_key=LITHE_AGILITY_ABILITY_KEY,
        )
    assert not drukhari_rules_unit_can_empower_for_ability(
        state,
        player_id="player-b",
        unit_instance_id=player_b_unit.unit_instance_id,
        pain_ability_key=LITHE_AGILITY_ABILITY_KEY,
    )

    empowered_payload = power_from_pain_empowerment_payload(
        unit_instance_id=unit.unit_instance_id,
        target_unit_instance_ids=(unit.unit_instance_id,),
        trigger="advance",
        phase=BattlePhaseKind.MOVEMENT,
        pain_ability_keys=(LITHE_AGILITY_ABILITY_KEY,),
        source_context={"test": "empowered"},
    )
    state.record_persisting_effect(
        _persisting_effect(
            effect_id="drukhari-test:pain-empowered-direct",
            unit_instance_id=unit.unit_instance_id,
            owner_player_id="player-a",
            effect_payload=empowered_payload,
        )
    )
    assert unit_is_empowered_through_pain_for_ability(
        state=state,
        player_id="player-a",
        unit_instance_id=unit.unit_instance_id,
        pain_ability_key=LITHE_AGILITY_ABILITY_KEY,
    )
    assert not drukhari_rules_unit_can_empower_for_ability(
        state,
        player_id="player-a",
        unit_instance_id=unit.unit_instance_id,
        pain_ability_key=LITHE_AGILITY_ABILITY_KEY,
    )

    malformed_state = _battle_state()
    malformed_unit = _unit_for_player(malformed_state, player_id="player-a")
    malformed_state.record_persisting_effect(
        _persisting_effect(
            effect_id="drukhari-test:malformed-pain-effect",
            unit_instance_id=malformed_unit.unit_instance_id,
            owner_player_id="player-a",
            effect_payload=[],
        )
    )
    with pytest.raises(GameLifecycleError):
        unit_is_empowered_through_pain_for_ability(
            state=malformed_state,
            player_id="player-a",
            unit_instance_id=malformed_unit.unit_instance_id,
            pain_ability_key=LITHE_AGILITY_ABILITY_KEY,
        )

    malformed_keys_state = _battle_state()
    malformed_keys_unit = _unit_for_player(malformed_keys_state, player_id="player-a")
    malformed_keys_state.record_persisting_effect(
        _persisting_effect(
            effect_id="drukhari-test:malformed-pain-keys",
            unit_instance_id=malformed_keys_unit.unit_instance_id,
            owner_player_id="player-a",
            effect_payload={
                "effect_kind": "drukhari_power_from_pain_empowered",
                "pain_ability_keys": "lithe_agility",
            },
        )
    )
    with pytest.raises(GameLifecycleError):
        unit_is_empowered_through_pain_for_ability(
            state=malformed_keys_state,
            player_id="player-a",
            unit_instance_id=malformed_keys_unit.unit_instance_id,
            pain_ability_key=LITHE_AGILITY_ABILITY_KEY,
        )

    non_power_state = _battle_state()
    non_power_unit = _unit_for_player(non_power_state, player_id="player-a")
    non_power_state.record_persisting_effect(
        _persisting_effect(
            effect_id="drukhari-test:source-backed-other-rule",
            unit_instance_id=non_power_unit.unit_instance_id,
            owner_player_id="player-a",
            effect_payload=source_backed_reroll_permission_effect_payload(
                target_unit_instance_ids=(non_power_unit.unit_instance_id,),
                permission=lithe_agility_advance_reroll_permission(
                    state=non_power_state,
                    player_id="player-a",
                    unit_instance_id=non_power_unit.unit_instance_id,
                ),
                source_payload={"effect_kind": "different_rule"},
            ),
        )
    )
    assert not unit_is_empowered_through_pain_for_ability(
        state=non_power_state,
        player_id="player-a",
        unit_instance_id=non_power_unit.unit_instance_id,
        pain_ability_key=LITHE_AGILITY_ABILITY_KEY,
    )

    invalid_payload_cases: tuple[Callable[[], object], ...] = (
        lambda: power_from_pain_empowerment_payload(
            unit_instance_id=unit.unit_instance_id,
            target_unit_instance_ids=cast(tuple[str, ...], []),
            trigger="advance",
            phase=BattlePhaseKind.MOVEMENT,
            pain_ability_keys=(LITHE_AGILITY_ABILITY_KEY,),
            source_context={},
        ),
        lambda: power_from_pain_empowerment_payload(
            unit_instance_id=unit.unit_instance_id,
            target_unit_instance_ids=(),
            trigger="advance",
            phase=BattlePhaseKind.MOVEMENT,
            pain_ability_keys=(LITHE_AGILITY_ABILITY_KEY,),
            source_context={},
        ),
        lambda: power_from_pain_empowerment_payload(
            unit_instance_id=unit.unit_instance_id,
            target_unit_instance_ids=(unit.unit_instance_id, unit.unit_instance_id),
            trigger="advance",
            phase=BattlePhaseKind.MOVEMENT,
            pain_ability_keys=(LITHE_AGILITY_ABILITY_KEY,),
            source_context={},
        ),
        lambda: power_from_pain_empowerment_payload(
            unit_instance_id=unit.unit_instance_id,
            target_unit_instance_ids=(unit.unit_instance_id,),
            trigger="advance",
            phase=BattlePhaseKind.MOVEMENT,
            pain_ability_keys=cast(tuple[str, ...], []),
            source_context={},
        ),
        lambda: power_from_pain_empowerment_payload(
            unit_instance_id=unit.unit_instance_id,
            target_unit_instance_ids=(unit.unit_instance_id,),
            trigger="advance",
            phase=BattlePhaseKind.MOVEMENT,
            pain_ability_keys=(),
            source_context={},
        ),
        lambda: power_from_pain_empowerment_payload(
            unit_instance_id=unit.unit_instance_id,
            target_unit_instance_ids=(unit.unit_instance_id,),
            trigger="advance",
            phase=BattlePhaseKind.MOVEMENT,
            pain_ability_keys=(LITHE_AGILITY_ABILITY_KEY, LITHE_AGILITY_ABILITY_KEY),
            source_context={},
        ),
        lambda: power_from_pain_empowerment_payload(
            unit_instance_id=unit.unit_instance_id,
            target_unit_instance_ids=(unit.unit_instance_id,),
            trigger="advance",
            phase=BattlePhaseKind.MOVEMENT,
            pain_ability_keys=("unsupported",),
            source_context={},
        ),
    )
    for invalid_payload_case in invalid_payload_cases:
        with pytest.raises(GameLifecycleError):
            invalid_payload_case()


def test_power_from_pain_runtime_hooks_validate_skips_and_duplicate_events() -> None:
    state = _battle_state()
    decisions = DecisionController()
    unit = _unit_for_player(state, player_id="player-a")
    target_unit = _unit_for_player(state, player_id="player-b")
    manager = DiceRollManager(state.game_id, event_log=decisions.event_log)

    invalid_context_cases: tuple[Callable[[], object], ...] = (
        lambda: army_rule.lithe_agility_advance_grant(cast(AdvanceMoveContext, object())),
        lambda: army_rule.lithe_agility_charge_declaration_grant(
            cast(ChargeDeclarationContext, object())
        ),
        lambda: army_rule.resolve_command_phase_start(cast(CommandPhaseStartContext, object())),
        lambda: army_rule.resolve_battle_shock_outcome(cast(BattleShockOutcomeContext, object())),
        lambda: army_rule.resolve_enemy_unit_destroyed(cast(UnitDestroyedContext, object())),
    )
    for invalid_context_case in invalid_context_cases:
        with pytest.raises(GameLifecycleError):
            invalid_context_case()

    _set_current_battle_phase(state, BattlePhase.MOVEMENT)
    _mark_player_as_drukhari(
        state,
        player_id="player-a",
        datasheet_abilities=(_lithe_agility_ability(),),
    )
    state.gain_faction_resource(
        player_id="player-a",
        resource_kind=PAIN_TOKEN_RESOURCE_KIND,
        amount=1,
        source_id="drukhari-test:normal-move-token",
    )
    assert (
        army_rule.lithe_agility_advance_grant(
            AdvanceMoveContext(
                state=state,
                player_id="player-a",
                battle_round=state.battle_round,
                unit_instance_id=unit.unit_instance_id,
                movement_phase_action="normal_move",
                movement_request_id="drukhari-test:normal-move-request",
                movement_result_id="drukhari-test:normal-move-result",
            )
        )
        is None
    )

    no_token_state = _battle_state()
    _set_current_battle_phase(no_token_state, BattlePhase.CHARGE)
    _mark_player_as_drukhari(
        no_token_state,
        player_id="player-a",
        datasheet_abilities=(_lithe_agility_ability(),),
    )
    no_token_unit = _unit_for_player(no_token_state, player_id="player-a")
    assert (
        army_rule.lithe_agility_charge_declaration_grant(
            ChargeDeclarationContext(
                state=no_token_state,
                player_id="player-a",
                battle_round=no_token_state.battle_round,
                unit_instance_id=no_token_unit.unit_instance_id,
                selection_request_id="drukhari-test:no-token-charge-request",
                selection_result_id="drukhari-test:no-token-charge-result",
            )
        )
        is None
    )

    non_drukhari_command_state = _battle_state()
    non_drukhari_decisions = DecisionController()
    army_rule.resolve_command_phase_start(
        CommandPhaseStartContext(
            state=non_drukhari_command_state,
            decisions=non_drukhari_decisions,
            active_player_id="player-a",
        )
    )
    assert pain_tokens_available(non_drukhari_command_state, player_id="player-a") == 0
    assert non_drukhari_decisions.event_log.records == ()

    passed_result = _battle_shock_result_for_unit(
        state=state,
        manager=manager,
        player_id="player-b",
        unit_instance_id=target_unit.unit_instance_id,
        result_id="drukhari-test:passed-battle-shock",
        fixed_rolls=(6, 6),
    )
    army_rule.resolve_battle_shock_outcome(
        BattleShockOutcomeContext(
            state=state,
            decisions=decisions,
            dice_manager=manager,
            result=passed_result,
            active_player_id="player-b",
            phase=BattlePhase.COMMAND,
            auto_passed=False,
            phase_start_battle_shocked_unit_ids=(),
        )
    )
    assert pain_tokens_available(state, player_id="player-a") == 1

    failed_result = _battle_shock_result_for_unit(
        state=state,
        manager=manager,
        player_id="player-b",
        unit_instance_id=target_unit.unit_instance_id,
        result_id="drukhari-test:duplicate-battle-shock",
        fixed_rolls=(1, 1),
    )
    failed_context = BattleShockOutcomeContext(
        state=state,
        decisions=decisions,
        dice_manager=manager,
        result=failed_result,
        active_player_id="player-b",
        phase=BattlePhase.COMMAND,
        auto_passed=False,
        phase_start_battle_shocked_unit_ids=(),
    )
    army_rule.resolve_battle_shock_outcome(failed_context)
    army_rule.resolve_battle_shock_outcome(failed_context)
    assert pain_tokens_available(state, player_id="player-a") == 2

    same_player_result = _battle_shock_result_for_unit(
        state=state,
        manager=manager,
        player_id="player-a",
        unit_instance_id=unit.unit_instance_id,
        result_id="drukhari-test:same-player-battle-shock",
        fixed_rolls=(1, 1),
    )
    army_rule.resolve_battle_shock_outcome(
        BattleShockOutcomeContext(
            state=state,
            decisions=decisions,
            dice_manager=manager,
            result=same_player_result,
            active_player_id="player-a",
            phase=BattlePhase.COMMAND,
            auto_passed=False,
            phase_start_battle_shocked_unit_ids=(),
        )
    )
    assert pain_tokens_available(state, player_id="player-a") == 2

    non_drukhari_destroyed_state = _battle_state()
    non_drukhari_destroyed_decisions = DecisionController()
    non_drukhari_target = _unit_for_player(non_drukhari_destroyed_state, player_id="player-b")
    non_drukhari_event = non_drukhari_destroyed_decisions.event_log.append(
        "model_destroyed",
        {
            "game_id": non_drukhari_destroyed_state.game_id,
            "battle_round": non_drukhari_destroyed_state.battle_round,
            "active_player_id": non_drukhari_destroyed_state.active_player_id,
            "phase": BattlePhase.SHOOTING.value,
            "destroying_player_id": "player-a",
            "target_unit_instance_id": non_drukhari_target.unit_instance_id,
            "model_instance_id": non_drukhari_target.own_models[-1].model_instance_id,
        },
    )
    army_rule.resolve_enemy_unit_destroyed(
        UnitDestroyedContext(
            state=non_drukhari_destroyed_state,
            decisions=non_drukhari_destroyed_decisions,
            completed_phase=BattlePhase.SHOOTING,
            model_destroyed_event_id=non_drukhari_event.event_id,
            model_destroyed_payload=cast(dict[str, JsonValue], non_drukhari_event.payload),
            destroying_player_id="player-a",
            destroyed_unit_instance_id=non_drukhari_target.unit_instance_id,
            destroyed_player_id="player-b",
        )
    )
    assert pain_tokens_available(non_drukhari_destroyed_state, player_id="player-a") == 0

    destroyed_state = _battle_state()
    _mark_player_as_drukhari(destroyed_state, player_id="player-a")
    destroyed_decisions = DecisionController()
    destroyed_target = _unit_for_player(destroyed_state, player_id="player-b")
    destroyed_event = destroyed_decisions.event_log.append(
        "model_destroyed",
        {
            "game_id": destroyed_state.game_id,
            "battle_round": destroyed_state.battle_round,
            "active_player_id": destroyed_state.active_player_id,
            "phase": BattlePhase.SHOOTING.value,
            "destroying_player_id": "player-a",
            "target_unit_instance_id": destroyed_target.unit_instance_id,
            "model_instance_id": destroyed_target.own_models[-1].model_instance_id,
        },
    )
    destroyed_context = UnitDestroyedContext(
        state=destroyed_state,
        decisions=destroyed_decisions,
        completed_phase=BattlePhase.SHOOTING,
        model_destroyed_event_id=destroyed_event.event_id,
        model_destroyed_payload=cast(dict[str, JsonValue], destroyed_event.payload),
        destroying_player_id="player-a",
        destroyed_unit_instance_id=destroyed_target.unit_instance_id,
        destroyed_player_id="player-b",
    )
    army_rule.resolve_enemy_unit_destroyed(destroyed_context)
    army_rule.resolve_enemy_unit_destroyed(destroyed_context)
    assert pain_tokens_available(destroyed_state, player_id="player-a") == 1


def test_generic_phase_modules_do_not_import_drukhari_faction_code() -> None:
    root = Path(__file__).parents[2]
    for relative_path in (
        "src/warhammer40k_core/engine/phases/movement.py",
        "src/warhammer40k_core/engine/phases/charge.py",
    ):
        path = root / relative_path
        source_paths = (
            (path, *sorted(path.parent.glob("movement_*.py")))
            if path.name == "movement.py"
            else (path,)
        )
        source = "\n".join(source_path.read_text(encoding="utf-8") for source_path in source_paths)
        assert "drukhari_power_from_pain" not in source
        assert "warhammer_40000_11th.drukhari" not in source


def _mark_player_as_drukhari(
    state: GameState,
    *,
    player_id: str,
    datasheet_abilities: tuple[DatasheetAbilityDescriptor, ...] = (),
    faction_keywords: tuple[str, ...] = ("DRUKHARI",),
) -> None:
    updated_armies: list[ArmyDefinition] = []
    for army in state.army_definitions:
        if army.player_id != player_id:
            updated_armies.append(army)
            continue
        updated_armies.append(
            replace(
                army,
                detachment_selection=replace(
                    army.detachment_selection,
                    faction_id="drukhari",
                ),
                units=tuple(
                    replace(
                        unit,
                        faction_keywords=faction_keywords,
                        datasheet_abilities=datasheet_abilities or unit.datasheet_abilities,
                    )
                    for unit in army.units
                ),
            )
        )
    state.army_definitions = updated_armies


def _unit_for_player(state: GameState, *, player_id: str) -> UnitInstance:
    army = state.army_definition_for_player(player_id)
    if army is None:
        raise AssertionError(f"Missing army for {player_id}.")
    return army.units[0]


def _set_current_battle_phase(state: GameState, phase: BattlePhase) -> None:
    state.battle_phase_index = state.battle_phase_sequence.index(phase)


def _shooting_phase_handler(
    registry: ShootingUnitSelectedGrantRegistry,
) -> ShootingPhaseHandler:
    return ShootingPhaseHandler(
        ruleset_descriptor=RulesetDescriptor.warhammer_40000_eleventh(
            descriptor_version="core-v2-phase17g-drukhari-test"
        ),
        army_catalog=ArmyCatalog.phase9a_canonical_content_pack(),
        shooting_unit_selected_grant_hooks=registry,
    )


def _lifecycle_state(lifecycle: GameLifecycle) -> GameState:
    if lifecycle.state is None:
        raise AssertionError("Lifecycle state is missing.")
    return lifecycle.state


def _refresh_lifecycle_runtime_content(lifecycle: GameLifecycle) -> None:
    lifecycle._refresh_runtime_content_bundle_if_armies_mustered()  # pyright: ignore[reportPrivateUsage]


def _decision_request_from_status(status: LifecycleStatus) -> DecisionRequest:
    if status.status_kind is not LifecycleStatusKind.WAITING_FOR_DECISION:
        raise AssertionError(f"Expected waiting status, got {status.status_kind}.")
    request = status.decision_request
    if type(request) is not DecisionRequest:
        raise AssertionError("Expected a decision request.")
    return request


def _event_payloads(lifecycle: GameLifecycle, event_type: str) -> tuple[dict[str, object], ...]:
    return tuple(
        cast(dict[str, object], event.payload)
        for event in lifecycle.decision_controller.event_log.records
        if event.event_type == event_type
    )


def _attack_step_payload(
    events: tuple[dict[str, object], ...],
    step: AttackSequenceStep,
) -> dict[str, object]:
    for event in events:
        if event["step"] == step.value:
            return event
    raise AssertionError(f"Missing attack sequence step {step.value}.")


def _first_primary_melee_weapon_payload(
    proposal_request: MeleeDeclarationProposalRequest,
) -> dict[str, object]:
    for weapon in proposal_request.available_weapons:
        weapon_payload = cast(dict[str, object], weapon)
        if weapon_payload["is_extra_attacks"] is True:
            continue
        engaged_target_ids = cast(list[str], weapon_payload["engaged_target_unit_instance_ids"])
        if engaged_target_ids:
            return weapon_payload
    raise AssertionError("Missing primary engaged melee weapon.")


def _lithe_agility_ability() -> DatasheetAbilityDescriptor:
    return DatasheetAbilityDescriptor(
        ability_id="drukhari-test-lithe-agility",
        name="Lithe Agility (Pain)",
        source_id="drukhari-test:lithe-agility",
        support=CatalogAbilitySupport.DESCRIPTOR_ONLY,
        source_kind=CatalogAbilitySourceKind.DATASHEET,
        parameter_tokens=(LITHE_AGILITY_ABILITY_KEY,),
        effect_description="When empowered, this unit can re-roll Advance and Charge rolls.",
    )


def _hatred_eternal_ability() -> DatasheetAbilityDescriptor:
    return DatasheetAbilityDescriptor(
        ability_id="drukhari-test-hatred-eternal",
        name="Hatred Eternal (Pain)",
        source_id="drukhari-test:hatred-eternal",
        support=CatalogAbilitySupport.DESCRIPTOR_ONLY,
        source_kind=CatalogAbilitySourceKind.DATASHEET,
        parameter_tokens=(HATRED_ETERNAL_ABILITY_KEY,),
        effect_description="When empowered, this unit can re-roll hit rolls.",
    )


def _battle_shock_result_for_unit(
    *,
    state: GameState,
    manager: DiceRollManager,
    player_id: str,
    unit_instance_id: str,
    result_id: str,
    fixed_rolls: tuple[int, int],
) -> BattleShockResult:
    request = BattleShockTestRequest(
        request_id=f"{result_id}:request",
        game_id=state.game_id,
        battle_round=state.battle_round,
        player_id=player_id,
        unit_instance_id=unit_instance_id,
        reason=BattleShockTestReason.BELOW_HALF_STRENGTH,
        leadership_target=7,
        below_half_strength_context=BelowHalfStrengthContext(
            player_id=player_id,
            unit_instance_id=unit_instance_id,
            starting_model_count=5,
            current_model_count=2,
            single_model_starting_wounds=None,
            single_model_wounds_remaining=None,
        ),
        spec=DiceRollSpec(
            expression=DiceExpression(quantity=2, sides=6),
            reason=f"Battle-shock test for {unit_instance_id}",
            roll_type=BATTLE_SHOCK_ROLL_TYPE,
            actor_id=unit_instance_id,
        ),
    )
    return BattleShockResult.from_roll_state(
        result_id=f"{result_id}:result",
        request=request,
        roll_state=manager.roll_fixed(request.spec, list(fixed_rolls)),
    )


def _persisting_effect(
    *,
    effect_id: str,
    unit_instance_id: str,
    owner_player_id: str,
    effect_payload: JsonValue,
    source_rule_id: str = SOURCE_RULE_ID,
) -> PersistingEffect:
    return PersistingEffect(
        effect_id=effect_id,
        source_rule_id=source_rule_id,
        owner_player_id=owner_player_id,
        target_unit_instance_ids=(unit_instance_id,),
        started_battle_round=1,
        started_phase=BattlePhaseKind.MOVEMENT,
        expiration=EffectExpiration.end_phase(
            battle_round=1,
            phase=BattlePhaseKind.MOVEMENT,
            player_id=owner_player_id,
        ),
        effect_payload=effect_payload,
    )


def _last_event_payload(decisions: DecisionController, event_type: str) -> dict[str, JsonValue]:
    for record in reversed(decisions.event_log.records):
        if record.event_type != event_type:
            continue
        payload = record.payload
        if not isinstance(payload, dict):
            raise TypeError(f"{event_type} payload is not an object.")
        return payload
    raise AssertionError(f"Missing event {event_type}.")
