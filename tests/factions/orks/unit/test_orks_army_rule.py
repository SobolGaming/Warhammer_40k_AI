from __future__ import annotations

import json
from collections.abc import Callable, Iterator
from copy import deepcopy
from dataclasses import replace
from typing import cast

import pytest

from tests.setup_completion_helpers import ensure_army_mustered_events_for_fixture
from warhammer40k_core.adapters.local_session import LocalGameSession
from warhammer40k_core.core.army_catalog import ArmyCatalog
from warhammer40k_core.core.attributes import Characteristic, CharacteristicValue
from warhammer40k_core.core.datasheet import DatasheetDefinition, DatasheetKeywordSet
from warhammer40k_core.core.detachment import DetachmentDefinition
from warhammer40k_core.core.dice import DiceExpression
from warhammer40k_core.core.faction import FactionDefinition
from warhammer40k_core.core.ruleset_descriptor import RulesetDescriptor
from warhammer40k_core.core.weapon_profiles import (
    AttackProfile,
    DamageProfile,
    RangeProfile,
    WeaponProfile,
)
from warhammer40k_core.engine.advance_eligibility_hooks import AdvanceEligibilityContext
from warhammer40k_core.engine.army_mustering import ArmyDefinition, ArmyMusterRequest, muster_army
from warhammer40k_core.engine.command_phase_start_hooks import (
    SELECT_FACTION_RULE_COMMAND_PHASE_START_OPTION_DECISION_TYPE,
    CommandPhaseStartRequestContext,
    CommandPhaseStartResultContext,
)
from warhammer40k_core.engine.decision_controller import DecisionController
from warhammer40k_core.engine.decision_request import DecisionRequest
from warhammer40k_core.engine.decision_result import DecisionResult
from warhammer40k_core.engine.effects import EffectExpirationBoundary
from warhammer40k_core.engine.event_log import validate_json_value
from warhammer40k_core.engine.faction_content.bundle import RuntimeContentBundle
from warhammer40k_core.engine.faction_content.warhammer_40000_11th.orks import army_rule
from warhammer40k_core.engine.game_state import (
    GameConfig,
    GameState,
    GameStatePayload,
    SecondaryMissionChoice,
    SecondaryMissionMode,
)
from warhammer40k_core.engine.lifecycle import GameLifecycle
from warhammer40k_core.engine.list_validation import (
    DetachmentSelection,
    UnitMusterSelection,
)
from warhammer40k_core.engine.mission_setup import MissionSetup
from warhammer40k_core.engine.phase import BattlePhase, GameLifecycleError, LifecycleStatusKind
from warhammer40k_core.engine.placement import create_deterministic_battlefield_scenario
from warhammer40k_core.engine.runtime_modifiers import (
    SaveOptionModifierContext,
    WeaponProfileModifierContext,
)
from warhammer40k_core.engine.saves import SaveKind, SaveOption
from warhammer40k_core.engine.setup_completion import SetupCompletionGate
from warhammer40k_core.engine.wargear_selections import (
    ModelProfileSelection,
)
from warhammer40k_core.rules.mission_pack_import import chapter_approved_2026_27_mission_pack

ORKS_DATASHEET_ID = "phase17g-orks-boyz"
ORKS_UNIT_ID = "army-alpha:boyz"
ENEMY_UNIT_ID = "army-beta:enemy-unit"


def test_lifecycle_requests_waaagh_call_and_records_active_effect() -> None:
    lifecycle = _battle_ready_lifecycle()
    contribution = army_rule.runtime_contribution()
    assert contribution.contribution_id == army_rule.CONTRIBUTION_ID
    assert not contribution.contribution_id.endswith(":scaffold")
    summary_payload = _runtime_content_bundle(lifecycle).to_summary_payload()
    assert army_rule.HOOK_ID in summary_payload["command_phase_start_hook_ids"]
    assert army_rule.ADVANCE_ELIGIBILITY_HOOK_ID in summary_payload["advance_eligibility_hook_ids"]
    assert army_rule.WEAPON_PROFILE_MODIFIER_ID in summary_payload["weapon_profile_modifier_ids"]
    assert army_rule.SAVE_OPTION_MODIFIER_ID in summary_payload["save_option_modifier_ids"]

    status = lifecycle.advance_until_decision_or_terminal()

    request = status.decision_request
    assert request is not None
    assert request.decision_type == SELECT_FACTION_RULE_COMMAND_PHASE_START_OPTION_DECISION_TYPE
    assert request.actor_id == "player-a"
    assert {option.option_id for option in request.options} == {
        army_rule.WAAAGH_CALL_OPTION_ID,
        army_rule.WAAAGH_DECLINE_OPTION_ID,
    }
    assert json.loads(json.dumps(request.to_payload())) == request.to_payload()

    result_status = lifecycle.submit_decision(
        DecisionResult.for_request(
            result_id="phase17g-orks-call-waaagh",
            request=request,
            selected_option_id=army_rule.WAAAGH_CALL_OPTION_ID,
        )
    )

    assert result_status.status_kind is not LifecycleStatusKind.INVALID
    state = _require_state(lifecycle)
    assert army_rule.waaagh_called_for_player(state, player_id="player-a")
    assert army_rule.waaagh_active_for_player(state, player_id="player-a")
    assert army_rule.waaagh_is_active_for_unit(state, unit_instance_id=ORKS_UNIT_ID)
    assert not army_rule.waaagh_active_for_player(state, player_id="player-b")
    restored = GameState.from_payload(
        cast(GameStatePayload, json.loads(json.dumps(state.to_payload())))
    )
    assert restored.to_payload() == state.to_payload()


def test_lifecycle_rejects_waaagh_drift_before_mutation() -> None:
    lifecycle = _battle_ready_lifecycle()
    status = lifecycle.advance_until_decision_or_terminal()
    request = status.decision_request
    assert request is not None
    option = request.option_by_id(army_rule.WAAAGH_CALL_OPTION_ID)

    actor_drift = lifecycle.submit_decision(
        DecisionResult(
            result_id="phase17g-orks-wrong-actor",
            request_id=request.request_id,
            decision_type=request.decision_type,
            actor_id="player-b",
            selected_option_id=option.option_id,
            payload=option.payload,
        )
    )

    assert actor_drift.status_kind is LifecycleStatusKind.INVALID
    assert isinstance(actor_drift.payload, dict)
    assert actor_drift.payload["invalid_reason"] == "invalid_command_phase_decision_result"
    assert actor_drift.payload["field"] == "actor_id"
    assert lifecycle.decision_controller.queue.peek_next() == request
    state = _require_state(lifecycle)
    assert not army_rule.waaagh_called_for_player(state, player_id="player-a")
    assert not army_rule.waaagh_active_for_player(state, player_id="player-a")

    malformed_payload = lifecycle.submit_decision(
        DecisionResult(
            result_id="phase17g-orks-malformed-payload",
            request_id=request.request_id,
            decision_type=request.decision_type,
            actor_id=request.actor_id,
            selected_option_id=option.option_id,
            payload="not-an-object",
        )
    )

    assert malformed_payload.status_kind is LifecycleStatusKind.INVALID
    assert isinstance(malformed_payload.payload, dict)
    assert malformed_payload.payload["invalid_reason"] == "invalid_command_phase_decision_result"
    assert malformed_payload.payload["field"] == "payload"
    assert lifecycle.decision_controller.queue.peek_next() == request
    assert not army_rule.waaagh_called_for_player(state, player_id="player-a")
    assert not army_rule.waaagh_active_for_player(state, player_id="player-a")

    drifted_payload = dict(cast(dict[str, object], option.payload))
    drifted_payload["battle_round"] = 99
    payload_drift = lifecycle.submit_decision(
        DecisionResult(
            result_id="phase17g-orks-payload-drift",
            request_id=request.request_id,
            decision_type=request.decision_type,
            actor_id=request.actor_id,
            selected_option_id=option.option_id,
            payload=validate_json_value(drifted_payload),
        )
    )

    assert payload_drift.status_kind is LifecycleStatusKind.INVALID
    assert isinstance(payload_drift.payload, dict)
    assert payload_drift.payload["invalid_reason"] == "invalid_command_phase_decision_result"
    assert payload_drift.payload["field"] == "payload"
    assert lifecycle.decision_controller.queue.peek_next() == request
    assert not army_rule.waaagh_called_for_player(state, player_id="player-a")
    assert not army_rule.waaagh_active_for_player(state, player_id="player-a")

    state.battle_round = 2
    stale_request = lifecycle.submit_decision(
        DecisionResult.for_request(
            result_id="phase17g-orks-stale-request",
            request=request,
            selected_option_id=option.option_id,
        )
    )

    assert stale_request.status_kind is LifecycleStatusKind.INVALID
    assert isinstance(stale_request.payload, dict)
    assert stale_request.payload["invalid_reason"] == "battle_round_drift"
    assert lifecycle.decision_controller.queue.peek_next() == request
    assert not army_rule.waaagh_called_for_player(state, player_id="player-a")
    assert not army_rule.waaagh_active_for_player(state, player_id="player-a")


def test_waaagh_decline_suppresses_only_current_command_phase_request() -> None:
    lifecycle = _battle_ready_lifecycle()
    request = _initial_waaagh_request(lifecycle)
    state = _require_state(lifecycle)

    assert army_rule.apply_waaagh_call_result(
        CommandPhaseStartResultContext(
            state=state,
            decisions=lifecycle.decision_controller,
            request=request,
            result=DecisionResult.for_request(
                result_id="phase17g-orks-decline-waaagh",
                request=request,
                selected_option_id=army_rule.WAAAGH_DECLINE_OPTION_ID,
            ),
            active_player_id="player-a",
        )
    )

    assert not army_rule.waaagh_called_for_player(state, player_id="player-a")
    assert not army_rule.waaagh_active_for_player(state, player_id="player-a")
    assert state.faction_rule_states_for_player(
        player_id="player-a",
        state_kind=army_rule.WAAAGH_DECLINE_STATE_KIND,
    )
    assert (
        army_rule.waaagh_call_request(
            CommandPhaseStartRequestContext(
                state=state,
                decisions=lifecycle.decision_controller,
                active_player_id="player-a",
            )
        )
        is None
    )


def test_waaagh_once_per_battle_state_survives_active_effect_expiry() -> None:
    lifecycle, _request = _state_after_direct_waaagh_call()
    state = _require_state(lifecycle)

    expired = state.expire_persisting_effects_at_boundary(
        EffectExpirationBoundary.turn_start(battle_round=2, player_id="player-a")
    )

    assert len(expired) == 1
    assert army_rule.waaagh_called_for_player(state, player_id="player-a")
    assert not army_rule.waaagh_active_for_player(state, player_id="player-a")
    assert (
        army_rule.waaagh_call_request(
            CommandPhaseStartRequestContext(
                state=state,
                decisions=lifecycle.decision_controller,
                active_player_id="player-a",
            )
        )
        is None
    )


def test_waaagh_advance_eligibility_grants_charge_after_advance() -> None:
    lifecycle, _request = _state_after_direct_waaagh_call()
    state = _require_state(lifecycle)

    grant = army_rule.waaagh_advance_eligibility(
        AdvanceEligibilityContext(
            state=state,
            player_id="player-a",
            battle_round=state.battle_round,
            unit_instance_id=ORKS_UNIT_ID,
            movement_request_id="phase17g-orks-move-request",
            movement_result_id="phase17g-orks-move-result",
        )
    )

    assert grant is not None
    assert grant.can_shoot is False
    assert grant.can_declare_charge is True
    assert grant.replay_payload is not None
    assert (
        army_rule.waaagh_advance_eligibility(
            AdvanceEligibilityContext(
                state=state,
                player_id="player-b",
                battle_round=state.battle_round,
                unit_instance_id=ENEMY_UNIT_ID,
                movement_request_id="phase17g-enemy-move-request",
                movement_result_id="phase17g-enemy-move-result",
            )
        )
        is None
    )
    with pytest.raises(GameLifecycleError, match="player drift"):
        army_rule.waaagh_advance_eligibility(
            AdvanceEligibilityContext(
                state=state,
                player_id="player-b",
                battle_round=state.battle_round,
                unit_instance_id=ORKS_UNIT_ID,
                movement_request_id="phase17g-orks-drift-move-request",
                movement_result_id="phase17g-orks-drift-move-result",
            )
        )


def test_waaagh_modifies_melee_weapon_strength_and_attacks_only_while_active() -> None:
    lifecycle, _request = _state_after_direct_waaagh_call()
    state = _require_state(lifecycle)
    melee_profile = _melee_weapon_profile()
    ranged_profile = _ranged_weapon_profile()

    modified = army_rule.waaagh_weapon_profile_modifier(
        _weapon_context(state=state, weapon_profile=melee_profile)
    )
    dice_modified = army_rule.waaagh_weapon_profile_modifier(
        _weapon_context(state=state, weapon_profile=_melee_dice_attack_profile())
    )

    assert modified.attack_profile.fixed_attacks == 3
    assert modified.strength.final == 5
    assert army_rule.SOURCE_RULE_ID in modified.source_ids
    assert dice_modified.attack_profile.dice_expression == DiceExpression(
        quantity=1,
        sides=3,
        modifier=0,
    )
    assert dice_modified.attack_profile.resolve_value(2) == 3
    operation = dice_modified.attack_profile.modifiers[0]
    assert operation.source_id == army_rule.SOURCE_RULE_ID
    assert (
        dice_modified.attack_profile.resolve_value(2, ignored_modifier_ids=(operation.modifier_id,))
        == 2
    )
    assert (
        army_rule.waaagh_weapon_profile_modifier(
            _weapon_context(state=state, weapon_profile=ranged_profile)
        )
        == ranged_profile
    )
    assert (
        army_rule.waaagh_weapon_profile_modifier(
            _weapon_context(
                state=state,
                weapon_profile=melee_profile,
                source_phase=BattlePhase.SHOOTING,
            )
        )
        == melee_profile
    )


def test_waaagh_adds_or_improves_five_plus_invulnerable_save() -> None:
    lifecycle, _request = _state_after_direct_waaagh_call()
    state = _require_state(lifecycle)
    armour = SaveOption(
        save_kind=SaveKind.ARMOUR,
        target_number=4,
        characteristic_target_number=4,
        armor_penetration=0,
        source_rule_ids=("phase17g:orks:test-armour",),
    )
    weak_invulnerable = SaveOption(
        save_kind=SaveKind.INVULNERABLE,
        target_number=6,
        characteristic_target_number=6,
        armor_penetration=0,
        source_rule_ids=("phase17g:orks:test-invulnerable",),
    )
    strong_invulnerable = replace(
        weak_invulnerable,
        target_number=4,
        characteristic_target_number=4,
    )

    added = army_rule.waaagh_save_option_modifier(
        SaveOptionModifierContext(
            state=state,
            target_unit_instance_id=ORKS_UNIT_ID,
            save_options=(armour,),
        )
    )
    improved = army_rule.waaagh_save_option_modifier(
        SaveOptionModifierContext(
            state=state,
            target_unit_instance_id=ORKS_UNIT_ID,
            save_options=(armour, weak_invulnerable),
        )
    )
    unchanged = army_rule.waaagh_save_option_modifier(
        SaveOptionModifierContext(
            state=state,
            target_unit_instance_id=ORKS_UNIT_ID,
            save_options=(armour, strong_invulnerable),
        )
    )
    enemy_options = army_rule.waaagh_save_option_modifier(
        SaveOptionModifierContext(
            state=state,
            target_unit_instance_id=ENEMY_UNIT_ID,
            save_options=(armour,),
        )
    )

    added_invulnerable = next(
        option for option in added if option.save_kind is SaveKind.INVULNERABLE
    )
    improved_invulnerable = next(
        option for option in improved if option.save_kind is SaveKind.INVULNERABLE
    )
    assert added_invulnerable.target_number == 5
    assert added_invulnerable.characteristic_target_number == 5
    assert army_rule.SOURCE_RULE_ID in added_invulnerable.source_rule_ids
    assert improved_invulnerable.target_number == 5
    assert improved_invulnerable.characteristic_target_number == 5
    assert army_rule.SOURCE_RULE_ID in improved_invulnerable.source_rule_ids
    assert unchanged[0] == armour
    assert (
        unchanged[1].characteristic_target_number
        == strong_invulnerable.characteristic_target_number
    )
    assert unchanged[1].characteristic_trace is not None
    assert unchanged[1].characteristic_trace.modifiers[0].source_id == army_rule.SOURCE_RULE_ID
    assert enemy_options == (armour,)


def _state_after_direct_waaagh_call() -> tuple[GameLifecycle, DecisionRequest]:
    lifecycle = _battle_ready_lifecycle()
    request = _initial_waaagh_request(lifecycle)
    state = _require_state(lifecycle)
    result = DecisionResult.for_request(
        result_id="phase17g-orks-direct-call-waaagh",
        request=request,
        selected_option_id=army_rule.WAAAGH_CALL_OPTION_ID,
    )
    assert army_rule.apply_waaagh_call_result(
        CommandPhaseStartResultContext(
            state=state,
            decisions=lifecycle.decision_controller,
            request=request,
            result=result,
            active_player_id="player-a",
        )
    )
    return lifecycle, request


def _initial_waaagh_request(lifecycle: GameLifecycle) -> DecisionRequest:
    status = lifecycle.advance_until_decision_or_terminal()
    request = status.decision_request
    assert request is not None
    return request


def _battle_ready_lifecycle(*, config: GameConfig | None = None) -> GameLifecycle:
    config = _orks_config() if config is None else config
    lifecycle = GameLifecycle()
    lifecycle.start(config)
    state = _require_state(lifecycle)
    for army in _mustered_armies(config):
        state.record_army_definition(army)
    scenario = create_deterministic_battlefield_scenario(
        battlefield_id="phase17g-orks-battlefield",
        armies=tuple(state.army_definitions),
    )
    state.record_battlefield_state(scenario.battlefield_state)
    state.record_secondary_mission_choice(_fixed_secondary_choice(player_id="player-a"))
    state.record_secondary_mission_choice(_fixed_secondary_choice(player_id="player-b"))
    _complete_setup_through_gate(
        state=state,
        decisions=lifecycle.decision_controller,
        config=config,
    )
    _runtime_content_bundle(lifecycle)
    return lifecycle


def _orks_config() -> GameConfig:
    catalog = _orks_lifecycle_catalog()
    return GameConfig(
        game_id="phase17g-orks-lifecycle-game",
        allow_legacy_non_strict_rosters=True,
        ruleset_descriptor=RulesetDescriptor.warhammer_40000_eleventh_chapter_approved_2026_27(
            descriptor_version="core-v2-phase17g-orks-test",
        ),
        army_catalog=catalog,
        army_muster_requests=(
            ArmyMusterRequest(
                army_id="army-alpha",
                player_id="player-a",
                catalog_id=catalog.catalog_id,
                source_package_id=catalog.source_package_id,
                ruleset_id=catalog.ruleset_id,
                detachment_selection=DetachmentSelection(
                    faction_id=army_rule.ORKS_FACTION_ID,
                    detachment_ids=("war-horde",),
                ),
                force_disposition_id="take-and-hold",
                unit_selections=(_unit_selection("boyz", ORKS_DATASHEET_ID),),
            ),
            ArmyMusterRequest(
                army_id="army-beta",
                player_id="player-b",
                catalog_id=catalog.catalog_id,
                source_package_id=catalog.source_package_id,
                ruleset_id=catalog.ruleset_id,
                detachment_selection=DetachmentSelection(
                    faction_id="core-marine-force",
                    detachment_ids=("core-combined-arms",),
                ),
                force_disposition_id="purge-the-foe",
                unit_selections=(_unit_selection("enemy-unit", "core-intercessor-like-infantry"),),
            ),
        ),
        player_ids=("player-a", "player-b"),
        turn_order=("player-a", "player-b"),
        fixed_secondary_mission_ids=("assassination", "bring_it_down"),
        mission_setup=_mission_setup(),
    )


def _orks_lifecycle_catalog() -> ArmyCatalog:
    base_catalog = ArmyCatalog.phase9a_canonical_content_pack()
    base_datasheet = base_catalog.datasheet_by_id("core-intercessor-like-infantry")
    return replace(
        base_catalog,
        datasheets=(
            *base_catalog.datasheets,
            _datasheet(
                base_datasheet,
                datasheet_id=ORKS_DATASHEET_ID,
                name="Boyz",
                keywords=("Infantry", "Battleline"),
                faction_keywords=("Orks",),
            ),
        ),
        factions=(
            *base_catalog.factions,
            FactionDefinition(
                faction_id=army_rule.ORKS_FACTION_ID,
                name="Orks",
                faction_keywords=("Orks",),
                source_ids=("phase17g:orks:faction",),
            ),
        ),
        detachments=(
            *base_catalog.detachments,
            DetachmentDefinition(
                canonical_detachment_id="war-horde",
                detachment_id="war-horde",
                name="War Horde",
                faction_id=army_rule.ORKS_FACTION_ID,
                detachment_point_cost=1,
                unit_datasheet_ids=(ORKS_DATASHEET_ID,),
                force_disposition_ids=("phase17g-force", "take-and-hold"),
                source_ids=("phase17g:orks:detachment:war-horde",),
            ),
        ),
    )


def _datasheet(
    base_datasheet: DatasheetDefinition,
    *,
    datasheet_id: str,
    name: str,
    keywords: tuple[str, ...],
    faction_keywords: tuple[str, ...],
) -> DatasheetDefinition:
    return replace(
        base_datasheet,
        datasheet_id=datasheet_id,
        name=name,
        keywords=DatasheetKeywordSet(
            keywords=keywords,
            faction_keywords=faction_keywords,
        ),
        source_ids=(f"phase17g:orks:datasheet:{datasheet_id}",),
    )


def _unit_selection(unit_selection_id: str, datasheet_id: str) -> UnitMusterSelection:
    return UnitMusterSelection(
        unit_selection_id=unit_selection_id,
        datasheet_id=datasheet_id,
        model_profile_selections=(
            ModelProfileSelection(
                model_profile_id="core-intercessor-like",
                model_count=5,
            ),
        ),
    )


def _mustered_armies(config: GameConfig) -> tuple[ArmyDefinition, ...]:
    return tuple(
        muster_army(catalog=config.army_catalog, request=request)
        for request in config.army_muster_requests
    )


def _fixed_secondary_choice(*, player_id: str) -> SecondaryMissionChoice:
    return SecondaryMissionChoice(
        player_id=player_id,
        mode=SecondaryMissionMode.FIXED,
        fixed_mission_ids=("assassination", "bring_it_down"),
    )


def _complete_setup_through_gate(
    *,
    state: GameState,
    decisions: DecisionController,
    config: GameConfig,
) -> None:
    ensure_army_mustered_events_for_fixture(state, decisions=decisions)
    final_setup_step = state.setup_sequence[-1]
    while state.current_setup_step is not final_setup_step:
        state.complete_current_setup_step()
    SetupCompletionGate().complete_setup_and_enter_battle(
        state=state,
        decisions=decisions,
        config=config,
    )


def _mission_setup() -> MissionSetup:
    return MissionSetup.from_mission_pack(
        mission_pack=chapter_approved_2026_27_mission_pack(),
        mission_pool_entry_id="mission-take-and-hold-vs-purge-the-foe-layout-3",
        terrain_layout_id="take-and-hold-vs-purge-the-foe-layout-3",
        attacker_player_id="player-a",
        attacker_force_disposition_id="take-and-hold",
        defender_player_id="player-b",
        defender_force_disposition_id="purge-the-foe",
    )


def _weapon_context(
    *,
    state: GameState,
    weapon_profile: WeaponProfile,
    source_phase: BattlePhase = BattlePhase.FIGHT,
) -> WeaponProfileModifierContext:
    return WeaponProfileModifierContext(
        state=state,
        source_phase=source_phase,
        attacking_unit_instance_id=ORKS_UNIT_ID,
        attacker_model_instance_id=f"{ORKS_UNIT_ID}:model-001",
        target_unit_instance_id=ENEMY_UNIT_ID,
        weapon_profile=weapon_profile,
    )


def _melee_weapon_profile() -> WeaponProfile:
    return WeaponProfile(
        profile_id="phase17g-orks-choppa",
        name="Choppa",
        range_profile=RangeProfile.melee(),
        attack_profile=AttackProfile.fixed(2),
        skill=CharacteristicValue.from_raw(Characteristic.WEAPON_SKILL, 3),
        strength=CharacteristicValue.from_raw(Characteristic.STRENGTH, 4),
        armor_penetration=CharacteristicValue.from_raw(Characteristic.ARMOR_PENETRATION, 0),
        damage_profile=DamageProfile.fixed(1),
        source_ids=("phase17g:orks:test-melee-weapon",),
    )


def _melee_dice_attack_profile() -> WeaponProfile:
    return replace(
        _melee_weapon_profile(),
        profile_id="phase17g-orks-dice-choppa",
        attack_profile=AttackProfile.dice(DiceExpression(quantity=1, sides=3)),
    )


def _ranged_weapon_profile() -> WeaponProfile:
    return WeaponProfile(
        profile_id="phase17g-orks-shoota",
        name="Shoota",
        range_profile=RangeProfile.distance(18),
        attack_profile=AttackProfile.fixed(2),
        skill=CharacteristicValue.from_raw(Characteristic.BALLISTIC_SKILL, 5),
        strength=CharacteristicValue.from_raw(Characteristic.STRENGTH, 4),
        armor_penetration=CharacteristicValue.from_raw(Characteristic.ARMOR_PENETRATION, 0),
        damage_profile=DamageProfile.fixed(1),
        source_ids=("phase17g:orks:test-ranged-weapon",),
    )


def _require_state(lifecycle: GameLifecycle) -> GameState:
    if lifecycle.state is None:
        raise AssertionError("lifecycle state is required")
    return lifecycle.state


def _runtime_content_bundle(lifecycle: GameLifecycle) -> RuntimeContentBundle:
    require_runtime_content_bundle = cast(
        Callable[[], RuntimeContentBundle],
        object.__getattribute__(lifecycle, "_require_runtime_content_bundle"),
    )
    return require_runtime_content_bundle()


@pytest.fixture(scope="session")
def shared_orks_config() -> Iterator[GameConfig]:
    """Reuse definitions only; each case deep-copies its complete mutable graph."""
    config = _orks_config()
    before = json.dumps(config.to_payload(), sort_keys=True)
    yield config
    assert json.dumps(config.to_payload(), sort_keys=True) == before


def _native_orks_session(config: GameConfig) -> LocalGameSession:
    return LocalGameSession(lifecycle=_battle_ready_lifecycle(config=deepcopy(config)))


def _native_waaagh_choice(session: LocalGameSession, option_id: str) -> None:
    request = _initial_waaagh_request(session.lifecycle)
    assert request.actor_id == "player-a"
    assert {o.option_id for o in request.options} == {
        army_rule.WAAAGH_CALL_OPTION_ID,
        army_rule.WAAAGH_DECLINE_OPTION_ID,
    }
    assert json.loads(json.dumps(request.to_payload())) == request.to_payload()
    status = session.submit_option(
        request_id=request.request_id, option_id=option_id, result_id="batch14:waaagh"
    )
    assert status.status_kind is not LifecycleStatusKind.INVALID


def test_native_waaagh_call_routes_loaded_consumers_then_expires_once(
    shared_orks_config: GameConfig,
) -> None:
    """Command choice -> loaded grants -> expiry; component queries, not a full battle."""
    session = _native_orks_session(shared_orks_config)
    state = _require_state(session.lifecycle)
    bundle = _runtime_content_bundle(session.lifecycle)
    registry = bundle.runtime_modifier_registry
    context = replace(
        _weapon_context(state=state, weapon_profile=_melee_weapon_profile()),
        attacker_model_instance_id=state.army_definitions[0].units[0].own_model_ids()[0],
    )
    assert registry.modified_weapon_profile(context) == context.weapon_profile
    _native_waaagh_choice(session, army_rule.WAAAGH_CALL_OPTION_ID)
    assert army_rule.waaagh_called_for_player(state, player_id="player-a")
    assert army_rule.waaagh_active_for_player(state, player_id="player-a")
    assert not army_rule.waaagh_active_for_player(state, player_id="player-b")
    called = [
        e
        for e in session.lifecycle.decision_controller.event_log.records
        if e.event_type == "orks_waaagh_called"
    ]
    assert len(called) == 1
    assert isinstance(called[0].payload, dict)
    assert called[0].payload["target_unit_instance_ids"] == [ORKS_UNIT_ID]
    assert called[0].payload["source_rule_id"] == army_rule.SOURCE_RULE_ID
    summary = bundle.to_summary_payload()
    assert army_rule.HOOK_ID in summary["command_phase_start_hook_ids"]
    assert army_rule.ADVANCE_ELIGIBILITY_HOOK_ID in summary["advance_eligibility_hook_ids"]
    assert army_rule.WEAPON_PROFILE_MODIFIER_ID in summary["weapon_profile_modifier_ids"]
    assert army_rule.SAVE_OPTION_MODIFIER_ID in summary["save_option_modifier_ids"]

    modified = registry.modified_weapon_profile(context)
    assert modified.attack_profile.fixed_attacks == 3
    assert modified.strength.final == 5
    assert army_rule.SOURCE_RULE_ID in modified.source_ids
    random_context = replace(context, weapon_profile=_melee_dice_attack_profile())
    random_profile = registry.modified_weapon_profile(random_context)
    assert random_profile.attack_profile.dice_expression == DiceExpression(1, 3)
    assert random_profile.attack_profile.resolve_value(2) == 3
    operation = random_profile.attack_profile.modifiers[0]
    assert operation.source_id == army_rule.SOURCE_RULE_ID
    assert (
        random_profile.attack_profile.resolve_value(
            2, ignored_modifier_ids=(operation.modifier_id,)
        )
        == 2
    )
    for neutral in (
        replace(context, weapon_profile=_ranged_weapon_profile()),
        replace(context, source_phase=BattlePhase.SHOOTING),
        replace(
            context,
            attacking_unit_instance_id=ENEMY_UNIT_ID,
            attacker_model_instance_id=state.army_definitions[1].units[0].own_model_ids()[0],
            target_unit_instance_id=ORKS_UNIT_ID,
        ),
    ):
        assert registry.modified_weapon_profile(neutral) == neutral.weapon_profile

    armour = SaveOption(SaveKind.ARMOUR, 4, 4, 0, source_rule_ids=("batch14:armour",))
    save_context = SaveOptionModifierContext(state, ORKS_UNIT_ID, (armour,))
    for existing, expected in ((None, 5), (6, 5), (4, 4)):
        options = (
            (armour,)
            if existing is None
            else (
                armour,
                SaveOption(
                    SaveKind.INVULNERABLE,
                    existing,
                    existing,
                    0,
                    source_rule_ids=("batch14:invuln",),
                ),
            )
        )
        actual = registry.modified_save_options(replace(save_context, save_options=options))
        assert actual[0] == armour
        invulnerable = next(o for o in actual if o.save_kind is SaveKind.INVULNERABLE)
        assert invulnerable.target_number == expected
        assert invulnerable.characteristic_target_number == expected
        if existing == 4:
            assert invulnerable.characteristic_trace is not None
            assert (
                invulnerable.characteristic_trace.modifiers[0].source_id == army_rule.SOURCE_RULE_ID
            )
        else:
            assert army_rule.SOURCE_RULE_ID in invulnerable.source_rule_ids
    assert registry.modified_save_options(
        replace(save_context, target_unit_instance_id=ENEMY_UNIT_ID)
    ) == (armour,)

    advance = AdvanceEligibilityContext(
        state, "player-a", state.battle_round, ORKS_UNIT_ID, "batch14:move", "batch14:result"
    )
    grants = bundle.advance_eligibility_hook_registry.grants_for(advance)
    own = next(g for g in grants if g.source_id == army_rule.SOURCE_RULE_ID)
    assert not own.can_shoot
    assert own.can_declare_charge
    assert isinstance(own.replay_payload, dict)
    assert own.replay_payload["unit_instance_id"] == ORKS_UNIT_ID
    assert own.replay_payload["can_declare_charge_after_advance"] is True
    assert (
        bundle.advance_eligibility_hook_registry.grants_for(
            replace(advance, player_id="player-b", unit_instance_id=ENEMY_UNIT_ID)
        )
        == ()
    )
    with pytest.raises(GameLifecycleError, match="player drift"):
        bundle.advance_eligibility_hook_registry.grants_for(replace(advance, player_id="player-b"))

    # Ordinary GameState round-trip only. This does not certify complete session replay.
    restored = GameState.from_payload(
        cast(GameStatePayload, json.loads(json.dumps(state.to_payload())))
    )
    assert restored.to_payload() == state.to_payload()
    assert army_rule.waaagh_called_for_player(restored, player_id="player-a")
    assert (
        len(
            restored.expire_persisting_effects_at_boundary(
                EffectExpirationBoundary.turn_start(battle_round=2, player_id="player-a")
            )
        )
        == 1
    )
    assert army_rule.waaagh_called_for_player(restored, player_id="player-a")
    assert not army_rule.waaagh_active_for_player(restored, player_id="player-a")
    assert (
        registry.modified_weapon_profile(replace(context, state=restored)) == context.weapon_profile
    )
    assert registry.modified_save_options(replace(save_context, state=restored)) == (armour,)
    assert (
        bundle.advance_eligibility_hook_registry.grants_for(replace(advance, state=restored)) == ()
    )
    restored.battle_phase_index = restored.battle_phase_sequence.index(BattlePhase.COMMAND)
    assert (
        army_rule.waaagh_call_request(
            CommandPhaseStartRequestContext(
                restored, session.lifecycle.decision_controller, "player-a"
            )
        )
        is None
    )
    # Expiring the independent round-trip graph cannot expire the live game.
    assert army_rule.waaagh_active_for_player(state, player_id="player-a")


def test_native_waaagh_decline_keeps_resource_and_reoffers_in_later_command(
    shared_orks_config: GameConfig,
) -> None:
    session = _native_orks_session(shared_orks_config)
    _native_waaagh_choice(session, army_rule.WAAAGH_DECLINE_OPTION_ID)
    state = _require_state(session.lifecycle)
    assert not army_rule.waaagh_called_for_player(state, player_id="player-a")
    assert not army_rule.waaagh_active_for_player(state, player_id="player-a")
    assert (
        len(
            state.faction_rule_states_for_player(
                player_id="player-a", state_kind=army_rule.WAAAGH_DECLINE_STATE_KIND
            )
        )
        == 1
    )
    state.battle_phase_index = state.battle_phase_sequence.index(BattlePhase.COMMAND)
    context = CommandPhaseStartRequestContext(
        state, session.lifecycle.decision_controller, "player-a"
    )
    assert army_rule.waaagh_call_request(context) is None
    # Explicit next-own-Command query checkpoint; intervening turns are not traversed.
    state.battle_round = 2
    state.battle_phase_index = state.battle_phase_sequence.index(BattlePhase.COMMAND)
    request = army_rule.waaagh_call_request(context)
    assert request is not None
    assert army_rule.WAAAGH_CALL_OPTION_ID in {o.option_id for o in request.options}
    events = [
        e
        for e in session.lifecycle.decision_controller.event_log.records
        if e.event_type.startswith("orks_waaagh_")
    ]
    assert [e.event_type for e in events] == ["orks_waaagh_declined"]
    fresh = _native_orks_session(shared_orks_config)
    fresh_state = _require_state(fresh.lifecycle)
    assert fresh_state.faction_rule_states == []
    assert not army_rule.waaagh_called_for_player(fresh_state, player_id="player-a")
    assert _initial_waaagh_request(fresh.lifecycle).option_by_id(army_rule.WAAAGH_CALL_OPTION_ID)


def test_native_waaagh_invalid_choices_preserve_request_then_allow_legal_retry(
    shared_orks_config: GameConfig,
) -> None:
    session = _native_orks_session(shared_orks_config)
    lifecycle = session.lifecycle
    request = _initial_waaagh_request(lifecycle)
    option = request.option_by_id(army_rule.WAAAGH_CALL_OPTION_ID)
    state = _require_state(lifecycle)
    drift = dict(cast(dict[str, object], option.payload))
    drift["battle_round"] = 99
    for actor, payload, field in (
        ("player-b", option.payload, "actor_id"),
        ("player-a", "not-an-object", "payload"),
        ("player-a", validate_json_value(drift), "payload"),
    ):
        before = lifecycle.to_payload()
        status = lifecycle.submit_decision(
            DecisionResult(
                result_id=f"batch14:invalid:{field}:{actor}",
                request_id=request.request_id,
                decision_type=request.decision_type,
                actor_id=actor,
                selected_option_id=option.option_id,
                payload=payload,
            )
        )
        assert status.status_kind is LifecycleStatusKind.INVALID
        assert isinstance(status.payload, dict)
        assert status.payload["invalid_reason"] == "invalid_command_phase_decision_result"
        assert status.payload["field"] == field
        assert lifecycle.to_payload() == before
        assert lifecycle.decision_controller.queue.peek_next() == request
        assert not army_rule.waaagh_called_for_player(state, player_id="player-a")
    state.battle_round = 2
    before = lifecycle.to_payload()
    stale = lifecycle.submit_decision(
        DecisionResult.for_request(
            result_id="batch14:stale", request=request, selected_option_id=option.option_id
        )
    )
    assert stale.status_kind is LifecycleStatusKind.INVALID
    assert isinstance(stale.payload, dict)
    assert stale.payload["invalid_reason"] == "battle_round_drift"
    assert lifecycle.to_payload() == before
    state.battle_round = 1
    status = session.submit_option(
        request_id=request.request_id, option_id=option.option_id, result_id="batch14:retry"
    )
    assert status.status_kind is not LifecycleStatusKind.INVALID
    assert army_rule.waaagh_called_for_player(state, player_id="player-a")
    assert (
        len(
            [
                e
                for e in lifecycle.decision_controller.event_log.records
                if e.event_type == "orks_waaagh_called"
            ]
        )
        == 1
    )
