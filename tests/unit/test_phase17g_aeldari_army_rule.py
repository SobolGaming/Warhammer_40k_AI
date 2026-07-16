from __future__ import annotations

import json
from collections.abc import Callable
from dataclasses import replace
from pathlib import Path
from typing import cast

import pytest
from tests.deployment_submission_helpers import submit_all_deployments_if_pending
from tests.movement_submission_helpers import (
    straight_line_witness_for_unit,
    submit_movement_proposal,
)

from warhammer40k_core.adapters.contracts import ParameterizedSubmission
from warhammer40k_core.core.army_catalog import ArmyCatalog
from warhammer40k_core.core.datasheet import DatasheetDefinition, DatasheetKeywordSet
from warhammer40k_core.core.detachment import DetachmentDefinition
from warhammer40k_core.core.faction import FactionDefinition
from warhammer40k_core.core.ruleset_descriptor import (
    ConsolidationModeKind,
    FightEligibilityKind,
    FightOrderingBandKind,
    FightPhaseStepKind,
    FightTypeKind,
    MovementMode,
    RulesetDescriptor,
)
from warhammer40k_core.core.weapon_profiles import WeaponKeyword
from warhammer40k_core.engine.advance_hooks import (
    DECLINE_MOVEMENT_ACTION_GRANT_OPTION_ID,
    SELECT_MOVEMENT_ACTION_GRANT_DECISION_TYPE,
)
from warhammer40k_core.engine.army_mustering import ArmyMusterRequest
from warhammer40k_core.engine.battlefield_state import (
    BattlefieldTransitionBatch,
    ModelDisplacementKind,
    ModelDisplacementRecord,
    ModelPlacement,
    UnitPlacement,
)
from warhammer40k_core.engine.charge_declaration_hooks import ChargeDeclarationContext
from warhammer40k_core.engine.decision_controller import DecisionController
from warhammer40k_core.engine.decision_request import DecisionError, DecisionRequest
from warhammer40k_core.engine.decision_result import DecisionResult
from warhammer40k_core.engine.effects import EffectExpirationKind, PersistingEffect
from warhammer40k_core.engine.event_log import JsonValue
from warhammer40k_core.engine.faction_content.bundle import RuntimeContentBundle
from warhammer40k_core.engine.faction_content.warhammer_40000_11th.aeldari import army_rule
from warhammer40k_core.engine.fight_activation_abilities import (
    FIGHT_ACTIVATION_ABILITY_DECISION_TYPE,
    FIGHT_ACTIVATION_MOVEMENT_DISTANCE_EFFECT_KIND,
    FightActivationAbilityContext,
)
from warhammer40k_core.engine.fight_order import (
    FIGHT_ACTIVATION_DECISION_TYPE,
    FightActivationSelection,
    FightMovementStepState,
    fight_activation_option_id,
)
from warhammer40k_core.engine.fight_resolution import (
    CONSOLIDATE_ACTION,
    FightMovementProposal,
    fight_movement_maximum_distance_inches,
)
from warhammer40k_core.engine.game_state import GameConfig, GameState
from warhammer40k_core.engine.lifecycle import GameLifecycle
from warhammer40k_core.engine.list_validation import (
    DetachmentSelection,
    UnitMusterSelection,
)
from warhammer40k_core.engine.mission_setup import MissionSetup
from warhammer40k_core.engine.movement_end_surge_hooks import MovementEndSurgeContext
from warhammer40k_core.engine.movement_proposals import (
    MOVEMENT_PROPOSAL_DECISION_TYPE,
    MovementProposalRequest,
    ProposalKind,
)
from warhammer40k_core.engine.phase import (
    BattlePhase,
    LifecycleStatus,
    LifecycleStatusKind,
)
from warhammer40k_core.engine.phases.movement import (
    SELECT_MOVEMENT_ACTION_DECISION_TYPE,
    SELECT_MOVEMENT_UNIT_DECISION_TYPE,
    MovementPhaseActionKind,
)
from warhammer40k_core.engine.phases.shooting import (
    SELECT_SHOOTING_TYPE_DECISION_TYPE,
    SELECT_SHOOTING_UNIT_DECISION_TYPE,
    SUBMIT_SHOOTING_DECLARATION_DECISION_TYPE,
    ShootingPhaseHandler,
)
from warhammer40k_core.engine.setup_flow import SECONDARY_MISSION_DECISION_TYPE
from warhammer40k_core.engine.shooting_end_surge_hooks import ShootingEndSurgeContext
from warhammer40k_core.engine.shooting_types import ShootingType
from warhammer40k_core.engine.stratagems import (
    DECLINE_STRATAGEM_WINDOW_OPTION_ID,
    STRATAGEM_DECISION_TYPE,
)
from warhammer40k_core.engine.wargear_selections import (
    ModelProfileSelection,
)
from warhammer40k_core.geometry.pose import Pose
from warhammer40k_core.rules.mission_pack_import import chapter_approved_2026_27_mission_pack

_AELDARI_UNIT_ID = "army-alpha:aeldari-vehicle"
_AELDARI_UNIT_SELECTION_ID = "aeldari-vehicle"
_AELDARI_DATASHEET_ID = "phase17g-aeldari-star-engine-vehicle"
_AELDARI_FIGHT_DATASHEET_ID = "phase17g-aeldari-sudden-strike-fighter"
_AELDARI_DETACHMENT_ID = "warhost"
_ENEMY_UNIT_SELECTION_ID = "enemy-unit"
_ENEMY_UNIT_ID = f"army-beta:{_ENEMY_UNIT_SELECTION_ID}"


def test_aeldari_battle_focus_agile_manoeuvres_text_is_source_backed_from_json() -> None:
    row = _wahapedia_aeldari_battle_focus_row()
    fields = cast(dict[str, JsonValue], row["fields"])
    description = cast(str, fields["description"])

    assert row["source_row_id"] == "000009894:AE"
    assert "AGILE MANOEUVRES\nSWIFT AS THE WIND" in description
    assert "FLITTING SHADOWS\nTRIGGER: When an eligible unit from your army" in description
    assert (
        "STAR ENGINES\n"
        "TRIGGER: When an eligible VEHICLE unit from your army is selected to make an "
        "Advance move.\n"
        "EFFECT: Until the end of the turn, Ranged weapons equipped by this unit have "
        "the [ASSAULT] ability."
    ) in description
    assert "SUDDEN STRIKE\nTRIGGER: When an eligible unit from your army is selected to fight." in (
        description
    )
    assert "OPPORTUNITY SEIZED\nTRIGGER: When an enemy unit ends a Fall Back move." in description
    assert "FADE BACK\nTRIGGER: In your opponent" in description
    assert "Shooting phase, just after an enemy unit has shot." in description


def test_aeldari_star_engines_grants_advanced_vehicle_assault_until_end_of_turn() -> None:
    config = _aeldari_config()
    lifecycle, movement_status = _advance_to_movement_unit_selection(config)
    bundle = _runtime_content_bundle(lifecycle)
    summary = bundle.to_summary_payload()
    assert {
        army_rule.SWIFT_AS_THE_WIND_HOOK_ID,
        army_rule.FLITTING_SHADOWS_HOOK_ID,
        army_rule.STAR_ENGINES_HOOK_ID,
    } <= set(summary["advance_move_hook_ids"])
    assert army_rule.OPPORTUNITY_SEIZED_HOOK_ID in summary["movement_end_surge_hook_ids"]
    assert army_rule.FLITTING_SHADOWS_HOOK_ID in summary["charge_declaration_hook_ids"]
    assert army_rule.FADE_BACK_HOOK_ID in summary["shooting_end_surge_hook_ids"]
    assert army_rule.SUDDEN_STRIKE_HOOK_ID in summary["fight_activation_ability_hook_ids"]

    action_status = lifecycle.submit_decision(
        DecisionResult.for_request(
            result_id="phase17g-aeldari-select-vehicle",
            request=_decision_request(movement_status),
            selected_option_id=_AELDARI_UNIT_ID,
        )
    )
    action_status = _decline_stratagem_window_if_present(
        lifecycle,
        action_status,
        result_id="phase17g-aeldari-decline-selected-to-move",
    )
    action_request = _decision_request(action_status)
    assert action_request.decision_type == SELECT_MOVEMENT_ACTION_DECISION_TYPE

    grant_status = lifecycle.submit_decision(
        DecisionResult.for_request(
            result_id="phase17g-aeldari-advance-action",
            request=action_request,
            selected_option_id=MovementPhaseActionKind.ADVANCE.value,
        )
    )
    grant_request = _decision_request(grant_status)
    assert grant_request.decision_type == SELECT_MOVEMENT_ACTION_GRANT_DECISION_TYPE
    assert {option.option_id for option in grant_request.options} == {
        DECLINE_MOVEMENT_ACTION_GRANT_OPTION_ID,
        army_rule.SWIFT_AS_THE_WIND_HOOK_ID,
        army_rule.FLITTING_SHADOWS_HOOK_ID,
        army_rule.HOOK_ID,
    }

    proposal_status = lifecycle.submit_decision(
        DecisionResult.for_request(
            result_id="phase17g-aeldari-star-engines",
            request=grant_request,
            selected_option_id=army_rule.HOOK_ID,
        )
    )
    proposal_request = _decision_request(proposal_status)
    assert proposal_request.decision_type == MOVEMENT_PROPOSAL_DECISION_TYPE
    advance_status = submit_movement_proposal(
        lifecycle,
        request=proposal_request,
        result_id="phase17g-aeldari-advance-proposal",
        unit_instance_id=_AELDARI_UNIT_ID,
        movement_phase_action=MovementPhaseActionKind.ADVANCE,
        movement_mode=MovementMode.ADVANCE,
        witness=straight_line_witness_for_unit(
            lifecycle,
            unit_instance_id=_AELDARI_UNIT_ID,
            dx=6.0,
        ),
    )
    _decline_stratagem_window_if_present(
        lifecycle,
        advance_status,
        result_id="phase17g-aeldari-decline-after-advance",
    )

    state = _state(lifecycle)
    advanced_state = state.advanced_unit_state_for_unit(
        player_id="player-a",
        battle_round=1,
        unit_instance_id=_AELDARI_UNIT_ID,
    )
    assert advanced_state is not None
    assert not advanced_state.can_shoot

    spend_effect = _single_persisting_effect_for_unit_by_kind(
        state,
        _AELDARI_UNIT_ID,
        army_rule.BATTLE_FOCUS_TOKEN_SPENT_EFFECT_KIND,
    )
    spend_payload = cast(dict[str, JsonValue], spend_effect.effect_payload)
    assert spend_effect.source_rule_id == army_rule.SOURCE_RULE_ID
    assert spend_effect.owner_player_id == "player-a"
    assert spend_effect.expiration.expiration_kind is EffectExpirationKind.END_BATTLE_ROUND
    assert spend_payload == {
        "effect_kind": army_rule.BATTLE_FOCUS_TOKEN_SPENT_EFFECT_KIND,
        "maneuver": army_rule.STAR_ENGINES_MANEUVER,
        "unit_instance_id": _AELDARI_UNIT_ID,
        "battle_focus_token_cost": 1,
        "movement_action_request_id": action_request.request_id,
        "movement_action_result_id": "phase17g-aeldari-advance-action",
    }

    grant_event = _event_payload(lifecycle, "movement_action_grant_decision_resolved")
    effect = _single_persisting_effect_for_unit_by_kind(
        state,
        _AELDARI_UNIT_ID,
        "ranged_weapon_keyword_grant",
    )
    effect_payload = cast(dict[str, JsonValue], effect.effect_payload)
    assert effect.source_rule_id == army_rule.SOURCE_RULE_ID
    assert effect.owner_player_id == "player-a"
    assert effect.target_unit_instance_ids == (_AELDARI_UNIT_ID,)
    assert effect.expiration.expiration_kind is EffectExpirationKind.END_TURN
    assert effect_payload == {
        "effect_kind": "ranged_weapon_keyword_grant",
        "granted_weapon_keywords": [WeaponKeyword.ASSAULT.value],
        "source_movement_request_id": action_request.request_id,
        "source_movement_result_id": "phase17g-aeldari-advance-action",
    }

    grants = cast(list[JsonValue], grant_event["selected_grants"])
    grant = cast(dict[str, JsonValue], grants[0])
    assert grant["hook_id"] == army_rule.HOOK_ID
    assert grant["source_id"] == army_rule.SOURCE_RULE_ID
    assert grant["label"] == "Battle Focus: Star Engines"
    assert grant["granted_ranged_weapon_keywords"] == [WeaponKeyword.ASSAULT.value]

    declaration_request = _shooting_declaration_request_for_aeldari_vehicle(
        state=state,
        config=config,
    )
    declaration_payload = cast(dict[str, JsonValue], declaration_request.payload)
    proposal = cast(dict[str, JsonValue], declaration_payload["proposal_request"])
    available_weapons = cast(list[JsonValue], proposal["available_weapons"])
    heavy_cannon = cast(dict[str, JsonValue], available_weapons[0])
    weapon_profile = cast(dict[str, JsonValue], heavy_cannon["weapon_profile"])

    assert declaration_request.decision_type == SUBMIT_SHOOTING_DECLARATION_DECISION_TYPE
    assert proposal["selected_shooting_type"] == ShootingType.ASSAULT.value
    assert heavy_cannon["wargear_id"] == "core-heavy-cannon"
    assert weapon_profile["keywords"] == [
        WeaponKeyword.ASSAULT.value,
        WeaponKeyword.HEAVY.value,
    ]
    assert army_rule.SOURCE_RULE_ID in cast(list[JsonValue], weapon_profile["source_ids"])


def test_aeldari_star_engines_decline_does_not_grant_assault() -> None:
    config = _aeldari_config()
    lifecycle, movement_status = _advance_to_movement_unit_selection(config)
    action_request = _select_aeldari_vehicle_for_movement(lifecycle, movement_status)

    grant_status = lifecycle.submit_decision(
        DecisionResult.for_request(
            result_id="phase17g-aeldari-decline-advance-action",
            request=action_request,
            selected_option_id=MovementPhaseActionKind.ADVANCE.value,
        )
    )
    grant_request = _decision_request(grant_status)
    assert grant_request.decision_type == SELECT_MOVEMENT_ACTION_GRANT_DECISION_TYPE

    proposal_status = lifecycle.submit_decision(
        DecisionResult.for_request(
            result_id="phase17g-aeldari-decline-star-engines",
            request=grant_request,
            selected_option_id=DECLINE_MOVEMENT_ACTION_GRANT_OPTION_ID,
        )
    )
    proposal_request = _decision_request(proposal_status)
    assert proposal_request.decision_type == MOVEMENT_PROPOSAL_DECISION_TYPE
    advance_status = submit_movement_proposal(
        lifecycle,
        request=proposal_request,
        result_id="phase17g-aeldari-decline-advance-proposal",
        unit_instance_id=_AELDARI_UNIT_ID,
        movement_phase_action=MovementPhaseActionKind.ADVANCE,
        movement_mode=MovementMode.ADVANCE,
        witness=straight_line_witness_for_unit(
            lifecycle,
            unit_instance_id=_AELDARI_UNIT_ID,
            dx=6.0,
        ),
    )
    _decline_stratagem_window_if_present(
        lifecycle,
        advance_status,
        result_id="phase17g-aeldari-decline-after-declined-advance",
    )

    state = _state(lifecycle)
    assert (
        _persisting_effects_for_unit_by_kind(
            state,
            _AELDARI_UNIT_ID,
            army_rule.BATTLE_FOCUS_TOKEN_SPENT_EFFECT_KIND,
        )
        == ()
    )
    assert (
        _persisting_effects_for_unit_by_kind(
            state,
            _AELDARI_UNIT_ID,
            "ranged_weapon_keyword_grant",
        )
        == ()
    )
    assert not _aeldari_vehicle_is_selectable_to_shoot(state=state, config=config)


def test_aeldari_star_engines_rejects_invented_advance_grant_option() -> None:
    config = _aeldari_config()
    lifecycle, movement_status = _advance_to_movement_unit_selection(config)
    action_request = _select_aeldari_vehicle_for_movement(lifecycle, movement_status)

    grant_status = lifecycle.submit_decision(
        DecisionResult.for_request(
            result_id="phase17g-aeldari-invalid-advance-action",
            request=action_request,
            selected_option_id=MovementPhaseActionKind.ADVANCE.value,
        )
    )
    grant_request = _decision_request(grant_status)
    assert grant_request.decision_type == SELECT_MOVEMENT_ACTION_GRANT_DECISION_TYPE

    with pytest.raises(DecisionError):
        lifecycle.submit_decision(
            DecisionResult(
                result_id="phase17g-aeldari-invented-star-engines",
                request_id=grant_request.request_id,
                decision_type=grant_request.decision_type,
                actor_id=grant_request.actor_id,
                selected_option_id="invented_star_engines",
                payload={
                    "submission_kind": SELECT_MOVEMENT_ACTION_GRANT_DECISION_TYPE,
                    "unit_instance_id": _AELDARI_UNIT_ID,
                    "movement_phase_action": MovementPhaseActionKind.ADVANCE.value,
                    "movement_mode": MovementMode.ADVANCE.value,
                    "source_decision_request_id": action_request.request_id,
                    "source_decision_result_id": "phase17g-aeldari-invalid-advance-action",
                    "selected_movement_action_grants": [],
                },
            )
        )

    assert (
        _persisting_effects_for_unit_by_kind(
            _state(lifecycle),
            _AELDARI_UNIT_ID,
            army_rule.BATTLE_FOCUS_TOKEN_SPENT_EFFECT_KIND,
        )
        == ()
    )


def test_aeldari_swift_as_the_wind_adds_two_inches_to_normal_move() -> None:
    config = _aeldari_config()
    lifecycle, movement_status = _advance_to_movement_unit_selection(config)
    action_request = _select_aeldari_vehicle_for_movement(lifecycle, movement_status)

    grant_status = lifecycle.submit_decision(
        DecisionResult.for_request(
            result_id="phase17g-aeldari-swift-normal-action",
            request=action_request,
            selected_option_id=MovementPhaseActionKind.NORMAL_MOVE.value,
        )
    )
    grant_request = _decision_request(grant_status)
    assert grant_request.decision_type == SELECT_MOVEMENT_ACTION_GRANT_DECISION_TYPE
    assert {option.option_id for option in grant_request.options} == {
        DECLINE_MOVEMENT_ACTION_GRANT_OPTION_ID,
        army_rule.SWIFT_AS_THE_WIND_HOOK_ID,
        army_rule.FLITTING_SHADOWS_HOOK_ID,
    }

    proposal_status = lifecycle.submit_decision(
        DecisionResult.for_request(
            result_id="phase17g-aeldari-swift-selected",
            request=grant_request,
            selected_option_id=army_rule.SWIFT_AS_THE_WIND_HOOK_ID,
        )
    )
    proposal_request = _decision_request(proposal_status)
    assert proposal_request.decision_type == MOVEMENT_PROPOSAL_DECISION_TYPE

    move_status = submit_movement_proposal(
        lifecycle,
        request=proposal_request,
        result_id="phase17g-aeldari-swift-move-proposal",
        unit_instance_id=_AELDARI_UNIT_ID,
        movement_phase_action=MovementPhaseActionKind.NORMAL_MOVE,
        movement_mode=MovementMode.NORMAL,
        witness=straight_line_witness_for_unit(
            lifecycle,
            unit_instance_id=_AELDARI_UNIT_ID,
            dx=12.0,
        ),
    )
    _decline_stratagem_window_if_present(
        lifecycle,
        move_status,
        result_id="phase17g-aeldari-decline-after-swift",
    )

    state = _state(lifecycle)
    agile_effect = _single_persisting_effect_for_unit_by_kind(
        state,
        _AELDARI_UNIT_ID,
        army_rule.AGILE_MANOEUVRE_EFFECT_KIND,
    )
    payload = cast(dict[str, JsonValue], agile_effect.effect_payload)
    assert agile_effect.expiration.expiration_kind is EffectExpirationKind.END_PHASE
    assert payload["maneuver"] == army_rule.SWIFT_AS_THE_WIND_MANEUVER
    assert payload["movement_bonus_inches"] == 2


def test_aeldari_flitting_shadows_movement_blocks_fire_overwatch_until_end_of_turn() -> None:
    config = _aeldari_config()
    lifecycle, movement_status = _advance_to_movement_unit_selection(config)
    action_request = _select_aeldari_vehicle_for_movement(lifecycle, movement_status)

    grant_status = lifecycle.submit_decision(
        DecisionResult.for_request(
            result_id="phase17g-aeldari-flitting-normal-action",
            request=action_request,
            selected_option_id=MovementPhaseActionKind.NORMAL_MOVE.value,
        )
    )
    grant_request = _decision_request(grant_status)
    proposal_status = lifecycle.submit_decision(
        DecisionResult.for_request(
            result_id="phase17g-aeldari-flitting-selected",
            request=grant_request,
            selected_option_id=army_rule.FLITTING_SHADOWS_HOOK_ID,
        )
    )
    proposal_request = _decision_request(proposal_status)
    move_status = submit_movement_proposal(
        lifecycle,
        request=proposal_request,
        result_id="phase17g-aeldari-flitting-move-proposal",
        unit_instance_id=_AELDARI_UNIT_ID,
        movement_phase_action=MovementPhaseActionKind.NORMAL_MOVE,
        movement_mode=MovementMode.NORMAL,
        witness=straight_line_witness_for_unit(
            lifecycle,
            unit_instance_id=_AELDARI_UNIT_ID,
            dx=6.0,
        ),
    )
    _decline_stratagem_window_if_present(
        lifecycle,
        move_status,
        result_id="phase17g-aeldari-decline-after-flitting",
    )

    effect = _single_persisting_effect_for_unit_by_kind(
        _state(lifecycle),
        _AELDARI_UNIT_ID,
        army_rule.AGILE_MANOEUVRE_EFFECT_KIND,
    )
    payload = cast(dict[str, JsonValue], effect.effect_payload)
    assert effect.expiration.expiration_kind is EffectExpirationKind.END_TURN
    assert payload["maneuver"] == army_rule.FLITTING_SHADOWS_MANEUVER
    assert payload["fire_overwatch_forbidden"] is True


def test_aeldari_flitting_shadows_charge_declaration_grant_blocks_overwatch() -> None:
    charge_state = _prepared_aeldari_state_at_phase(BattlePhase.CHARGE)
    context = ChargeDeclarationContext(
        state=charge_state,
        player_id="player-a",
        battle_round=charge_state.battle_round,
        unit_instance_id=_AELDARI_UNIT_ID,
        selection_request_id="phase17g-aeldari-charge-select-request",
        selection_result_id="phase17g-aeldari-charge-select-result",
    )

    grant = army_rule.flitting_shadows_charge_declaration_grant(context)

    assert grant is not None
    assert grant.hook_id == army_rule.FLITTING_SHADOWS_HOOK_ID
    assert grant.unit_effect_expiration == "end_turn"
    payload = cast(dict[str, JsonValue], grant.unit_effect_payload)
    assert payload["maneuver"] == army_rule.FLITTING_SHADOWS_MANEUVER
    assert payload["fire_overwatch_forbidden"] is True


def test_aeldari_sudden_strike_fight_option_extends_pile_in_and_consolidation() -> None:
    fight_state = _prepared_aeldari_state_at_phase(BattlePhase.FIGHT)
    activation = FightActivationSelection(
        player_id="player-a",
        battle_round=fight_state.battle_round,
        unit_instance_id=_AELDARI_UNIT_ID,
        ordering_band=FightOrderingBandKind.REMAINING_COMBATS,
        fight_type=FightTypeKind.NORMAL,
        eligibility_reasons=(FightEligibilityKind.CURRENTLY_ENGAGED,),
        request_id="phase17g-aeldari-fight-activation-request",
        result_id="phase17g-aeldari-fight-activation-result",
    )
    context = FightActivationAbilityContext(
        state=fight_state,
        game_id=fight_state.game_id,
        battle_round=fight_state.battle_round,
        active_player_id="player-a",
        player_id="player-a",
        unit_instance_id=_AELDARI_UNIT_ID,
        activation=activation,
        target_unit_instance_ids=(_ENEMY_UNIT_ID,),
    )

    option = army_rule.sudden_strike_fight_activation_option(context)

    assert option is not None
    assert option.hook_id == army_rule.SUDDEN_STRIKE_HOOK_ID
    assert option.ability_id == army_rule.SUDDEN_STRIKE_MANEUVER
    assert option.effect_kind == FIGHT_ACTIVATION_MOVEMENT_DISTANCE_EFFECT_KIND
    assert option.model_proximity_inches is None
    assert option.pile_in_distance_inches == 6.0
    assert option.consolidate_distance_inches == 6.0
    spend_payload = cast(dict[str, JsonValue], option.decision_effect_payload)
    assert spend_payload["maneuver"] == army_rule.SUDDEN_STRIKE_MANEUVER
    assert spend_payload["battle_focus_token_cost"] == 1


def test_aeldari_sudden_strike_fight_movement_distance_uses_lifecycle_effect() -> None:
    lifecycle, _movement_status = _advance_to_movement_unit_selection(
        _aeldari_config(
            aeldari_datasheet_id=_AELDARI_FIGHT_DATASHEET_ID,
            aeldari_model_profile_id="core-character-leader",
        )
    )
    state = _state(lifecycle)
    _place_unit_poses(
        state,
        unit_instance_id=_AELDARI_UNIT_ID,
        poses=(Pose.at(10.0, 20.0, 0.0),),
    )
    _place_unit_poses(
        state,
        unit_instance_id=_ENEMY_UNIT_ID,
        poses=_unit_line_poses(x=12.15, y=20.0),
    )
    _advance_lifecycle_state_to_phase(lifecycle, BattlePhase.FIGHT)
    lifecycle = _rehydrate_lifecycle_with_empty_decisions(lifecycle)
    state = _state(lifecycle)
    bundle = _runtime_content_bundle(lifecycle)
    summary = bundle.to_summary_payload()

    assert army_rule.SUDDEN_STRIKE_HOOK_ID in summary["fight_activation_ability_hook_ids"]

    activation_request = _decision_request(
        _drain_fight_movement_requests(
            lifecycle,
            lifecycle.advance_until_decision_or_terminal(),
        )
    )
    assert activation_request.decision_type == FIGHT_ACTIVATION_DECISION_TYPE

    ability_status = lifecycle.submit_decision(
        DecisionResult.for_request(
            result_id="phase17g-aeldari-sudden-strike-activation",
            request=activation_request,
            selected_option_id=fight_activation_option_id(
                unit_instance_id=_AELDARI_UNIT_ID,
                fight_type=FightTypeKind.NORMAL,
            ),
        )
    )
    ability_request = _decision_request(ability_status)
    assert ability_request.decision_type == FIGHT_ACTIVATION_ABILITY_DECISION_TYPE

    melee_status = lifecycle.submit_decision(
        DecisionResult.for_request(
            result_id="phase17g-aeldari-sudden-strike-use",
            request=ability_request,
            selected_option_id=f"use:{army_rule.SUDDEN_STRIKE_MANEUVER}",
        )
    )
    assert melee_status.status_kind is LifecycleStatusKind.WAITING_FOR_DECISION

    state = _state(lifecycle)
    assert (
        fight_movement_maximum_distance_inches(
            state=state,
            unit_instance_id=_AELDARI_UNIT_ID,
            proposal_kind=ProposalKind.PILE_IN,
        )
        == 6.0
    )
    assert (
        fight_movement_maximum_distance_inches(
            state=state,
            unit_instance_id=_AELDARI_UNIT_ID,
            proposal_kind=ProposalKind.CONSOLIDATE,
        )
        == 6.0
    )
    used_event = _last_event_payload(lifecycle, "fight_activation_ability_used")
    persisting_effect = cast(dict[str, JsonValue], used_event["persisting_effect"])
    effect_payload = cast(dict[str, JsonValue], persisting_effect["effect_payload"])
    assert effect_payload["effect_kind"] == FIGHT_ACTIVATION_MOVEMENT_DISTANCE_EFFECT_KIND
    assert effect_payload["pile_in_distance_inches"] == 6.0
    assert effect_payload["consolidate_distance_inches"] == 6.0

    _place_unit_poses(
        state,
        unit_instance_id=_AELDARI_UNIT_ID,
        poses=(Pose.at(10.0, 20.0, 0.0),),
    )
    _place_unit_poses(
        state,
        unit_instance_id=_ENEMY_UNIT_ID,
        poses=_unit_line_poses(x=14.0, y=20.0),
    )
    fight_state = state.fight_phase_state
    assert fight_state is not None
    policy = state.runtime_ruleset_descriptor().fight_policy
    state.fight_phase_state = (
        fight_state.with_active_activation(None)
        .with_consolidate_state(
            FightMovementStepState.start(
                step=FightPhaseStepKind.CONSOLIDATE,
                next_player_id="player-a",
            )
        )
        .with_current_step(current_step=FightPhaseStepKind.CONSOLIDATE, policy=policy)
    )
    lifecycle = _rehydrate_lifecycle_with_empty_decisions(lifecycle)
    consolidate_request = _decision_request(lifecycle.advance_until_decision_or_terminal())
    proposal_request = MovementProposalRequest.from_decision_request_payload(
        consolidate_request.payload
    )
    assert proposal_request.proposal_kind is ProposalKind.CONSOLIDATE
    assert proposal_request.context is not None
    assert proposal_request.context["maximum_distance_inches"] == 6.0

    consolidate_status = lifecycle.submit_decision(
        ParameterizedSubmission(
            request_id=consolidate_request.request_id,
            result_id="phase17g-aeldari-sudden-strike-consolidate",
            payload=cast(
                JsonValue,
                FightMovementProposal(
                    proposal_request_id=proposal_request.request_id,
                    proposal_kind=ProposalKind.CONSOLIDATE,
                    unit_instance_id=_AELDARI_UNIT_ID,
                    movement_phase_action=CONSOLIDATE_ACTION,
                    movement_mode=MovementMode.CONSOLIDATE,
                    consolidation_mode=ConsolidationModeKind.ENGAGING,
                    consolidate_target_unit_instance_ids=(_ENEMY_UNIT_ID,),
                    witness=straight_line_witness_for_unit(
                        lifecycle,
                        unit_instance_id=_AELDARI_UNIT_ID,
                        dx=2.5,
                        dy=2.0,
                    ),
                ).to_payload(),
            ),
        ).to_result(consolidate_request)
    )

    completed_event = _last_event_payload(lifecycle, "fight_movement_completed")
    resolution = cast(dict[str, JsonValue], completed_event["resolution"])
    assert consolidate_status.status_kind is not LifecycleStatusKind.INVALID
    assert completed_event["result_id"] == "phase17g-aeldari-sudden-strike-consolidate"
    assert resolution["maximum_distance_inches"] == 6.0


def test_aeldari_opportunity_seized_grants_d6_plus_one_after_enemy_fall_back() -> None:
    config = _aeldari_config()
    lifecycle, _movement_status = _advance_to_movement_unit_selection(config)
    state = _state(lifecycle)
    _place_unit_poses(
        state,
        unit_instance_id=_AELDARI_UNIT_ID,
        poses=(Pose.at(20.0, 20.0, 0.0),),
    )
    enemy_start_poses = _unit_line_poses(x=24.0, y=20.0)
    enemy_end_poses = _unit_line_poses(x=34.0, y=20.0)
    _place_unit_poses(state, unit_instance_id=_ENEMY_UNIT_ID, poses=enemy_end_poses)
    transition_batch = _displacement_batch_for_unit(
        state=state,
        unit_instance_id=_ENEMY_UNIT_ID,
        start_poses=enemy_start_poses,
        end_poses=enemy_end_poses,
    )
    context = MovementEndSurgeContext(
        state=state,
        ruleset_descriptor=config.ruleset_descriptor,
        triggering_unit_instance_id=_ENEMY_UNIT_ID,
        triggering_player_id="player-b",
        reacting_player_id="player-a",
        trigger_event_id="phase17g-aeldari-enemy-fall-back-event",
        movement_phase_action=MovementPhaseActionKind.FALL_BACK.value,
        trigger_event_payload={"transition_batch": cast(JsonValue, transition_batch.to_payload())},
    )

    grants = army_rule.opportunity_seized_surge_grants(context)

    assert len(grants) == 1
    grant = grants[0]
    assert grant.hook_id == army_rule.OPPORTUNITY_SEIZED_HOOK_ID
    assert grant.unit_instance_id == _AELDARI_UNIT_ID
    assert grant.max_distance_bonus_inches == 1
    payload = cast(dict[str, JsonValue], grant.decision_effect_payload)
    assert payload["maneuver"] == army_rule.OPPORTUNITY_SEIZED_MANEUVER


def test_aeldari_fade_back_grants_d6_plus_one_to_hit_unit_after_enemy_shoots() -> None:
    shooting_state = _prepared_aeldari_state_at_phase(BattlePhase.SHOOTING)
    context = ShootingEndSurgeContext(
        state=shooting_state,
        shooting_unit_instance_id=_ENEMY_UNIT_ID,
        shooting_player_id="player-b",
        reacting_player_id="player-a",
        trigger_event_id="phase17g-aeldari-enemy-shooting-event",
        hit_target_unit_instance_ids=(_AELDARI_UNIT_ID,),
    )

    grants = army_rule.fade_back_surge_grants(context)

    assert len(grants) == 1
    grant = grants[0]
    assert grant.hook_id == army_rule.FADE_BACK_HOOK_ID
    assert grant.unit_instance_id == _AELDARI_UNIT_ID
    assert grant.max_distance_bonus_inches == 1
    payload = cast(dict[str, JsonValue], grant.decision_effect_payload)
    assert payload["maneuver"] == army_rule.FADE_BACK_MANEUVER


def _wahapedia_aeldari_battle_focus_row() -> dict[str, JsonValue]:
    path = (
        Path("data/source_snapshots/wahapedia")
        / ("1" + "0th-edition")
        / "2026-06-14"
        / "json"
        / "Abilities.json"
    )
    artifact = json.loads(path.read_text(encoding="utf-8"))
    rows = cast(list[JsonValue], artifact["rows"])
    for row in rows:
        payload = cast(dict[str, JsonValue], row)
        fields = cast(dict[str, JsonValue], payload["fields"])
        if fields["name"] == "Battle Focus" and fields["faction_id"] == "AE":
            return payload
    raise AssertionError("missing Aeldari Battle Focus source row")


def _aeldari_config(
    *,
    aeldari_datasheet_id: str = _AELDARI_DATASHEET_ID,
    aeldari_model_profile_id: str = "core-vehicle-monster",
    aeldari_model_count: int = 1,
) -> GameConfig:
    catalog = _aeldari_catalog()
    return GameConfig(
        game_id="phase17g-aeldari-star-engines",
        allow_legacy_non_strict_rosters=True,
        ruleset_descriptor=RulesetDescriptor.warhammer_40000_eleventh(
            descriptor_version="core-v2-phase17g-aeldari-test"
        ),
        army_catalog=catalog,
        army_muster_requests=(
            _army_muster_request(
                catalog=catalog,
                army_id="army-alpha",
                player_id="player-a",
                faction_id=army_rule.AELDARI_FACTION_ID,
                detachment_id=_AELDARI_DETACHMENT_ID,
                unit_selection_id=_AELDARI_UNIT_SELECTION_ID,
                datasheet_id=aeldari_datasheet_id,
                model_profile_id=aeldari_model_profile_id,
                model_count=aeldari_model_count,
            ),
            _army_muster_request(
                catalog=catalog,
                army_id="army-beta",
                player_id="player-b",
                faction_id="core-marine-force",
                detachment_id="core-combined-arms",
                unit_selection_id=_ENEMY_UNIT_SELECTION_ID,
                datasheet_id="core-intercessor-like-infantry",
                model_profile_id="core-intercessor-like",
                model_count=5,
            ),
        ),
        player_ids=("player-a", "player-b"),
        turn_order=("player-a", "player-b"),
        fixed_secondary_mission_ids=("assassination", "bring_it_down", "cleanse"),
        mission_setup=_mission_setup(),
    )


def _aeldari_catalog() -> ArmyCatalog:
    base_catalog = ArmyCatalog.phase9a_canonical_content_pack()
    aeldari_vehicle = _aeldari_vehicle_datasheet(
        base_catalog.datasheet_by_id("core-vehicle-monster")
    )
    aeldari_fighter = _aeldari_fight_datasheet(
        base_catalog.datasheet_by_id("core-character-leader")
    )
    return replace(
        base_catalog,
        datasheets=(*base_catalog.datasheets, aeldari_vehicle, aeldari_fighter),
        factions=(
            *base_catalog.factions,
            FactionDefinition(
                faction_id=army_rule.AELDARI_FACTION_ID,
                name="Aeldari",
                faction_keywords=("Asuryani",),
                source_ids=("gw-11e-faction-detachments-2026-27:faction:aeldari",),
            ),
        ),
        detachments=(
            *base_catalog.detachments,
            DetachmentDefinition(
                detachment_id=_AELDARI_DETACHMENT_ID,
                name="Warhost",
                faction_id=army_rule.AELDARI_FACTION_ID,
                detachment_point_cost=3,
                unit_datasheet_ids=(_AELDARI_DATASHEET_ID, _AELDARI_FIGHT_DATASHEET_ID),
                force_disposition_ids=("phase17g-force",),
                source_ids=("gw-11e-faction-detachments-2026-27:detachment:aeldari:warhost",),
            ),
        ),
    )


def _aeldari_vehicle_datasheet(base_datasheet: DatasheetDefinition) -> DatasheetDefinition:
    return replace(
        base_datasheet,
        datasheet_id=_AELDARI_DATASHEET_ID,
        name="Star Engines Test Vehicle",
        keywords=DatasheetKeywordSet(
            keywords=("Vehicle",),
            faction_keywords=("Asuryani",),
        ),
        attachment_eligibilities=(),
        source_ids=("phase17g:test:aeldari:star-engines-vehicle",),
    )


def _aeldari_fight_datasheet(base_datasheet: DatasheetDefinition) -> DatasheetDefinition:
    return replace(
        base_datasheet,
        datasheet_id=_AELDARI_FIGHT_DATASHEET_ID,
        name="Sudden Strike Test Fighter",
        keywords=DatasheetKeywordSet(
            keywords=base_datasheet.keywords.keywords,
            faction_keywords=("Asuryani",),
        ),
        attachment_eligibilities=(),
        source_ids=("phase17g:test:aeldari:sudden-strike-fighter",),
    )


def _army_muster_request(
    *,
    catalog: ArmyCatalog,
    army_id: str,
    player_id: str,
    faction_id: str,
    detachment_id: str,
    unit_selection_id: str,
    datasheet_id: str,
    model_profile_id: str,
    model_count: int,
) -> ArmyMusterRequest:
    return ArmyMusterRequest(
        army_id=army_id,
        player_id=player_id,
        catalog_id=catalog.catalog_id,
        source_package_id=catalog.source_package_id,
        ruleset_id=catalog.ruleset_id,
        detachment_selection=DetachmentSelection(
            faction_id=faction_id,
            detachment_ids=(detachment_id,),
        ),
        force_disposition_id=(
            "purge-the-foe" if faction_id == "core-marine-force" else "phase17g-force"
        ),
        unit_selections=(
            UnitMusterSelection(
                unit_selection_id=unit_selection_id,
                datasheet_id=datasheet_id,
                model_profile_selections=(
                    ModelProfileSelection(
                        model_profile_id=model_profile_id,
                        model_count=model_count,
                    ),
                ),
            ),
        ),
    )


def _mission_setup() -> MissionSetup:
    return MissionSetup.from_mission_pack(
        mission_pack=chapter_approved_2026_27_mission_pack(),
        mission_pool_entry_id="mission-take-and-hold-vs-purge-the-foe-layout-3",
        terrain_layout_id="take-and-hold-vs-purge-the-foe-layout-3",
        attacker_player_id="player-a",
        defender_player_id="player-b",
    )


def _advance_to_movement_unit_selection(
    config: GameConfig,
) -> tuple[GameLifecycle, LifecycleStatus]:
    lifecycle = GameLifecycle()
    lifecycle.start(config)
    status = lifecycle.advance_until_decision_or_terminal()
    secondary_index = 1
    while (
        status.decision_request is not None
        and status.decision_request.decision_type == SECONDARY_MISSION_DECISION_TYPE
    ):
        status = lifecycle.submit_decision(
            DecisionResult.for_request(
                result_id=f"phase17g-aeldari-secondary-{secondary_index:06d}",
                request=_decision_request(status),
                selected_option_id="fixed:assassination:bring_it_down",
            )
        )
        secondary_index += 1
    status = submit_all_deployments_if_pending(
        lifecycle,
        status,
        result_id_prefix="phase17g-aeldari-deploy",
        pose_factory=_aeldari_shooting_reachable_deployment_pose,
    )
    request = _decision_request(status)
    assert request.decision_type == SELECT_MOVEMENT_UNIT_DECISION_TYPE
    return lifecycle, status


def _decline_stratagem_window_if_present(
    lifecycle: GameLifecycle,
    status: LifecycleStatus,
    *,
    result_id: str,
) -> LifecycleStatus:
    request = _decision_request(status)
    if request.decision_type != STRATAGEM_DECISION_TYPE:
        return status
    return lifecycle.submit_decision(
        DecisionResult.for_request(
            result_id=result_id,
            request=request,
            selected_option_id=DECLINE_STRATAGEM_WINDOW_OPTION_ID,
        )
    )


def _select_aeldari_vehicle_for_movement(
    lifecycle: GameLifecycle,
    movement_status: LifecycleStatus,
) -> DecisionRequest:
    action_status = lifecycle.submit_decision(
        DecisionResult.for_request(
            result_id="phase17g-aeldari-select-vehicle",
            request=_decision_request(movement_status),
            selected_option_id=_AELDARI_UNIT_ID,
        )
    )
    action_status = _decline_stratagem_window_if_present(
        lifecycle,
        action_status,
        result_id="phase17g-aeldari-decline-selected-to-move",
    )
    action_request = _decision_request(action_status)
    assert action_request.decision_type == SELECT_MOVEMENT_ACTION_DECISION_TYPE
    return action_request


def _aeldari_vehicle_is_selectable_to_shoot(
    *,
    state: GameState,
    config: GameConfig,
) -> bool:
    shooting_state = _state_at_phase(state, BattlePhase.SHOOTING)
    handler = ShootingPhaseHandler(
        ruleset_descriptor=config.ruleset_descriptor,
        army_catalog=config.army_catalog,
    )
    decisions = DecisionController()
    status = handler.begin_phase(state=shooting_state, decisions=decisions)
    if status.status_kind is not LifecycleStatusKind.WAITING_FOR_DECISION:
        return False
    request = _decision_request(status)
    if request.decision_type != SELECT_SHOOTING_UNIT_DECISION_TYPE:
        return False
    return _AELDARI_UNIT_ID in {option.option_id for option in request.options}


def _shooting_declaration_request_for_aeldari_vehicle(
    *,
    state: GameState,
    config: GameConfig,
) -> DecisionRequest:
    shooting_state = _state_at_phase(state, BattlePhase.SHOOTING)
    handler = ShootingPhaseHandler(
        ruleset_descriptor=config.ruleset_descriptor,
        army_catalog=config.army_catalog,
    )
    decisions = DecisionController()
    status = handler.begin_phase(state=shooting_state, decisions=decisions)
    unit_request = _decision_request(status)
    assert unit_request.decision_type == SELECT_SHOOTING_UNIT_DECISION_TYPE
    assert _AELDARI_UNIT_ID in {option.option_id for option in unit_request.options}

    handler.apply_decision(
        state=shooting_state,
        decisions=decisions,
        result=DecisionResult.for_request(
            result_id="phase17g-aeldari-select-shooting-unit",
            request=unit_request,
            selected_option_id=_AELDARI_UNIT_ID,
        ),
    )
    type_status = handler.begin_phase(state=shooting_state, decisions=decisions)
    type_request = _decision_request(type_status)
    assert type_request.decision_type == SELECT_SHOOTING_TYPE_DECISION_TYPE
    assert tuple(option.option_id for option in type_request.options) == (
        ShootingType.ASSAULT.value,
    )

    handler.apply_decision(
        state=shooting_state,
        decisions=decisions,
        result=DecisionResult.for_request(
            result_id="phase17g-aeldari-select-assault-shooting",
            request=type_request,
            selected_option_id=ShootingType.ASSAULT.value,
        ),
    )
    declaration_status = handler.begin_phase(state=shooting_state, decisions=decisions)
    return _decision_request(declaration_status)


def _aeldari_shooting_reachable_deployment_pose(
    index: int,
    player_id: str,
    model_instance_id: str,
) -> Pose:
    unit_instance_id = model_instance_id.rsplit(":", 2)[0]
    if unit_instance_id == _AELDARI_UNIT_ID:
        return Pose.at(15.5, 17.0, 0.0, facing_degrees=0.0)
    if unit_instance_id == f"army-beta:{_ENEMY_UNIT_SELECTION_ID}":
        return Pose.at(43.5, 17.0 + (index * 1.8), 0.0, facing_degrees=180.0)
    if player_id == "player-b":
        return Pose.at(57.0, 24.0 + (index * 1.8), 0.0, facing_degrees=180.0)
    return Pose.at(3.0, 24.0 + (index * 1.8), 0.0, facing_degrees=0.0)


def _state_at_phase(state: GameState, phase: BattlePhase) -> GameState:
    phase_state = GameState.from_payload(state.to_payload())
    while phase_state.current_battle_phase is not phase:
        if phase_state.current_battle_phase is None:
            raise AssertionError("battle state ended before expected phase")
        phase_state.advance_to_next_battle_phase()
    return phase_state


def _prepared_aeldari_state_at_phase(phase: BattlePhase) -> GameState:
    lifecycle, _status = _advance_to_movement_unit_selection(_aeldari_config())
    return _state_at_phase(_state(lifecycle), phase)


def _advance_lifecycle_state_to_phase(lifecycle: GameLifecycle, phase: BattlePhase) -> None:
    state = _state(lifecycle)
    while state.current_battle_phase is not phase:
        if state.current_battle_phase is None:
            raise AssertionError("battle state ended before expected phase")
        state.advance_to_next_battle_phase()


def _rehydrate_lifecycle_with_empty_decisions(lifecycle: GameLifecycle) -> GameLifecycle:
    payload = lifecycle.to_payload()
    payload["decisions"] = DecisionController().to_payload()
    return GameLifecycle.from_payload(payload)


def _drain_fight_movement_requests(
    lifecycle: GameLifecycle,
    status: LifecycleStatus,
) -> LifecycleStatus:
    current = status
    while (
        current.status_kind is LifecycleStatusKind.WAITING_FOR_DECISION
        and current.decision_request is not None
        and current.decision_request.decision_type == MOVEMENT_PROPOSAL_DECISION_TYPE
    ):
        request = current.decision_request
        proposal_request = MovementProposalRequest.from_decision_request_payload(request.payload)
        assert proposal_request.proposal_kind in {
            ProposalKind.PILE_IN,
            ProposalKind.CONSOLIDATE,
        }
        context = cast(dict[str, JsonValue], proposal_request.context)
        current = lifecycle.submit_decision(
            ParameterizedSubmission(
                request_id=request.request_id,
                result_id=f"{request.request_id}:phase17g-aeldari-no-move",
                payload=cast(
                    JsonValue,
                    {
                        "proposal_request_id": proposal_request.request_id,
                        "proposal_kind": proposal_request.proposal_kind.value,
                        "unit_instance_id": proposal_request.unit_instance_id,
                        "movement_phase_action": proposal_request.movement_phase_action,
                        "movement_mode": context["movement_mode"],
                    },
                ),
            ).to_result(request)
        )
    return current


def _place_unit_poses(
    state: GameState,
    *,
    unit_instance_id: str,
    poses: tuple[Pose, ...],
) -> None:
    if state.battlefield_state is None:
        raise AssertionError("test state requires battlefield_state")
    placement = state.battlefield_state.unit_placement_by_id(unit_instance_id)
    state.replace_battlefield_state(
        state.battlefield_state.with_unit_placement(_with_model_poses(placement, poses=poses))
    )


def _unit_line_poses(*, x: float, y: float) -> tuple[Pose, ...]:
    return tuple(Pose.at(x, y + index * 1.8, 0.0) for index in range(5))


def _with_model_poses(
    unit_placement: UnitPlacement,
    *,
    poses: tuple[Pose, ...],
) -> UnitPlacement:
    if len(poses) != len(unit_placement.model_placements):
        raise AssertionError("test pose fixture must match unit model count")
    return UnitPlacement(
        army_id=unit_placement.army_id,
        player_id=unit_placement.player_id,
        unit_instance_id=unit_placement.unit_instance_id,
        model_placements=tuple(
            ModelPlacement(
                army_id=placement.army_id,
                player_id=placement.player_id,
                unit_instance_id=placement.unit_instance_id,
                model_instance_id=placement.model_instance_id,
                pose=pose,
            )
            for placement, pose in zip(unit_placement.model_placements, poses, strict=True)
        ),
    )


def _displacement_batch_for_unit(
    *,
    state: GameState,
    unit_instance_id: str,
    start_poses: tuple[Pose, ...],
    end_poses: tuple[Pose, ...],
) -> BattlefieldTransitionBatch:
    if state.battlefield_state is None:
        raise AssertionError("test state requires battlefield_state")
    placement = state.battlefield_state.unit_placement_by_id(unit_instance_id)
    if len(start_poses) != len(placement.model_placements):
        raise AssertionError("test start poses must match unit model count")
    if len(end_poses) != len(placement.model_placements):
        raise AssertionError("test end poses must match unit model count")
    return BattlefieldTransitionBatch(
        displacements=tuple(
            ModelDisplacementRecord(
                model_instance_id=model_placement.model_instance_id,
                displacement_kind=ModelDisplacementKind.FALL_BACK,
                start_pose=start_pose,
                end_pose=end_pose,
                source_phase=BattlePhase.MOVEMENT.value,
                source_step="move_units",
                source_event_id="phase17g-aeldari-enemy-fall-back-event",
            )
            for model_placement, start_pose, end_pose in zip(
                placement.model_placements,
                start_poses,
                end_poses,
                strict=True,
            )
        )
    )


def _single_persisting_effect_for_unit_by_kind(
    state: GameState,
    unit_instance_id: str,
    effect_kind: str,
) -> PersistingEffect:
    effects = _persisting_effects_for_unit_by_kind(state, unit_instance_id, effect_kind)
    assert len(effects) == 1
    return effects[0]


def _persisting_effects_for_unit_by_kind(
    state: GameState,
    unit_instance_id: str,
    effect_kind: str,
) -> tuple[PersistingEffect, ...]:
    effects: list[PersistingEffect] = []
    for effect in state.persisting_effects_for_unit(unit_instance_id):
        payload = cast(dict[str, JsonValue], effect.effect_payload)
        if payload.get("effect_kind") == effect_kind:
            effects.append(effect)
    return tuple(effects)


def _runtime_content_bundle(lifecycle: GameLifecycle) -> RuntimeContentBundle:
    require_runtime_content_bundle = cast(
        Callable[[], RuntimeContentBundle],
        object.__getattribute__(lifecycle, "_require_runtime_content_bundle"),
    )
    return require_runtime_content_bundle()


def _event_payload(lifecycle: GameLifecycle, event_type: str) -> dict[str, JsonValue]:
    for event in lifecycle.decision_controller.event_log.records:
        if event.event_type == event_type:
            return cast(dict[str, JsonValue], event.payload)
    raise AssertionError(f"missing event {event_type}")


def _last_event_payload(lifecycle: GameLifecycle, event_type: str) -> dict[str, JsonValue]:
    for event in reversed(lifecycle.decision_controller.event_log.records):
        if event.event_type == event_type:
            return cast(dict[str, JsonValue], event.payload)
    raise AssertionError(f"missing event {event_type}")


def _decision_request(status: LifecycleStatus) -> DecisionRequest:
    assert status.status_kind is LifecycleStatusKind.WAITING_FOR_DECISION
    assert status.decision_request is not None
    return status.decision_request


def _state(lifecycle: GameLifecycle) -> GameState:
    assert lifecycle.state is not None
    return lifecycle.state
