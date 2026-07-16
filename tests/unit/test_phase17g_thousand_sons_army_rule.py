from __future__ import annotations

import json
from collections.abc import Callable
from dataclasses import replace
from typing import cast

from tests.movement_submission_helpers import straight_line_witness_for_unit

from warhammer40k_core.core.army_catalog import ArmyCatalog
from warhammer40k_core.core.attributes import Characteristic, CharacteristicValue
from warhammer40k_core.core.datasheet import (
    CatalogAbilitySourceKind,
    CatalogAbilitySupport,
    DatasheetAbilityDescriptor,
    DatasheetDefinition,
    DatasheetKeywordSet,
)
from warhammer40k_core.core.detachment import DetachmentDefinition
from warhammer40k_core.core.faction import FactionDefinition
from warhammer40k_core.core.ruleset_descriptor import MovementMode, RulesetDescriptor
from warhammer40k_core.core.weapon_profiles import (
    AttackProfile,
    DamageProfile,
    RangeProfile,
    WeaponProfile,
)
from warhammer40k_core.engine.army_mustering import ArmyDefinition, ArmyMusterRequest, muster_army
from warhammer40k_core.engine.decision_controller import DecisionController
from warhammer40k_core.engine.decision_request import (
    PARAMETERIZED_DECISION_OPTION_ID,
    DecisionOption,
    DecisionRequest,
)
from warhammer40k_core.engine.decision_result import DecisionResult
from warhammer40k_core.engine.event_log import JsonValue, validate_json_value
from warhammer40k_core.engine.faction_content.bundle import RuntimeContentBundle
from warhammer40k_core.engine.faction_content.warhammer_40000_11th.thousand_sons import (
    army_rule,
)
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
from warhammer40k_core.engine.movement_proposals import (
    MOVEMENT_PROPOSAL_DECISION_TYPE,
    MovementProposalPayload,
    MovementProposalRequest,
)
from warhammer40k_core.engine.phase import BattlePhase, LifecycleStatus, LifecycleStatusKind
from warhammer40k_core.engine.phases.shooting import ShootingPhaseState
from warhammer40k_core.engine.placement import create_deterministic_battlefield_scenario
from warhammer40k_core.engine.runtime_modifiers import WeaponProfileModifierContext
from warhammer40k_core.engine.setup_completion import SetupCompletionGate
from warhammer40k_core.engine.shooting_phase_start_hooks import (
    SELECT_FACTION_RULE_SHOOTING_PHASE_START_OPTION_DECISION_TYPE,
)
from warhammer40k_core.engine.source_backed_rerolls import (
    source_backed_reroll_permission_context_for_unit,
)
from warhammer40k_core.engine.triggered_movement import TRIGGERED_MOVEMENT_PROPOSAL_ACTION
from warhammer40k_core.engine.wargear_selections import (
    ModelProfileSelection,
)
from warhammer40k_core.geometry.pose import Pose
from warhammer40k_core.rules.mission_pack_import import chapter_approved_2026_27_mission_pack

MANIFESTER_ID = "army-alpha:rubric-marines"
FRIENDLY_TARGET_ID = "army-alpha:scarab-occult"
ENEMY_UNIT_ID = "army-beta:enemy-unit"
ENEMY_OTHER_ID = "army-beta:enemy-unit-2"
ENEMY_LONE_OPERATIVE_ID = "army-beta:lone-operative"
MANIFESTER_DATASHEET_ID = "phase17g-thousand-sons-rubrics"
FRIENDLY_TARGET_DATASHEET_ID = "phase17g-thousand-sons-scarab-occult"
ENEMY_LONE_OPERATIVE_DATASHEET_ID = "phase17g-thousand-sons-lone-operative"
THOUSAND_SONS_DETACHMENT_ID = "phase17g-thousand-sons-grand-coven"
OPFOR_DETACHMENT_ID = "phase17g-thousand-sons-opfor"


def test_lifecycle_requests_cabal_and_destinys_ruin_records_hit_reroll() -> None:
    lifecycle = _battle_ready_lifecycle(game_id="phase17g-thousand-sons-destiny")
    contribution = army_rule.runtime_contribution()
    assert contribution.contribution_id == army_rule.CONTRIBUTION_ID
    assert not contribution.contribution_id.endswith(":scaffold")
    summary = _runtime_content_bundle(lifecycle).to_summary_payload()
    assert army_rule.HOOK_ID in summary["shooting_phase_start_hook_ids"]
    assert army_rule.WEAPON_PROFILE_MODIFIER_ID in summary["weapon_profile_modifier_ids"]
    assert (
        army_rule.MORTAL_WOUND_FEEL_NO_PAIN_HOOK_ID in summary["mortal_wound_feel_no_pain_hook_ids"]
    )

    request = _next_cabal_request(lifecycle)

    assert request.decision_type == SELECT_FACTION_RULE_SHOOTING_PHASE_START_OPTION_DECISION_TYPE
    assert request.actor_id == "player-a"
    assert json.loads(json.dumps(request.to_payload())) == request.to_payload()
    assert _done_option(request).option_id == army_rule.CABAL_DONE_OPTION_ID
    option = _ritual_option(
        request,
        ritual_id=army_rule.CabalRitualId.DESTINYS_RUIN.value,
        target_rules_unit_id=ENEMY_UNIT_ID,
        channel_the_warp=False,
    )

    status = lifecycle.submit_decision(
        DecisionResult.for_request(
            result_id="phase17g-thousand-sons-destiny-result",
            request=request,
            selected_option_id=option.option_id,
        )
    )

    assert status.status_kind is not LifecycleStatusKind.INVALID
    state = _require_state(lifecycle)
    attempt_states = state.faction_rule_states_for_player(
        player_id="player-a",
        state_kind=army_rule.CABAL_ATTEMPT_STATE_KIND,
    )
    assert len(attempt_states) == 1
    attempt_payload = cast(dict[str, JsonValue], attempt_states[0].payload)
    assert attempt_payload["ritual_id"] == army_rule.CabalRitualId.DESTINYS_RUIN.value
    permission_context = source_backed_reroll_permission_context_for_unit(
        state=state,
        player_id="player-a",
        unit_instance_id=MANIFESTER_ID,
        roll_type="attack_sequence.hit",
        timing_window="attack_sequence.hit",
        target_unit_instance_id=ENEMY_UNIT_ID,
    )
    assert permission_context is not None
    assert permission_context.source_payload["target_unit_instance_id"] == ENEMY_UNIT_ID
    assert permission_context.source_payload["reroll_mode"] == "ones"
    assert permission_context.source_payload["conditional_hit_reroll"] == {
        "reroll_unmodified_values": [1],
    }
    restored = GameState.from_payload(
        cast(GameStatePayload, json.loads(json.dumps(state.to_payload())))
    )
    assert restored.to_payload() == state.to_payload()


def test_twist_of_fate_modifies_ap_and_rejects_drift_or_closed_window() -> None:
    lifecycle = _battle_ready_lifecycle(game_id="phase17g-thousand-sons-twist")
    request = _next_cabal_request(lifecycle)
    option = _ritual_option(
        request,
        ritual_id=army_rule.CabalRitualId.TWIST_OF_FATE.value,
        target_rules_unit_id=ENEMY_UNIT_ID,
        channel_the_warp=True,
    )

    status = lifecycle.submit_decision(
        DecisionResult.for_request(
            result_id="phase17g-thousand-sons-twist-result",
            request=request,
            selected_option_id=option.option_id,
        )
    )

    assert status.status_kind is not LifecycleStatusKind.INVALID
    state = _require_state(lifecycle)
    modified = army_rule.cabal_weapon_profile_modifier(
        _weapon_context(
            state=state,
            attacking_unit_instance_id=MANIFESTER_ID,
            target_unit_instance_id=ENEMY_UNIT_ID,
            weapon_profile=_ranged_weapon_profile(),
        )
    )
    assert modified.armor_penetration.final in {-1, -2}
    assert army_rule.SOURCE_RULE_ID in modified.source_ids
    unmodified = army_rule.cabal_weapon_profile_modifier(
        _weapon_context(
            state=state,
            attacking_unit_instance_id=MANIFESTER_ID,
            target_unit_instance_id=ENEMY_OTHER_ID,
            weapon_profile=_ranged_weapon_profile(),
        )
    )
    assert unmodified == _ranged_weapon_profile()

    drift_lifecycle = _battle_ready_lifecycle(game_id="phase17g-thousand-sons-drift")
    drift_request = _next_cabal_request(drift_lifecycle)
    drift_option = _ritual_option(
        drift_request,
        ritual_id=army_rule.CabalRitualId.DESTINYS_RUIN.value,
        target_rules_unit_id=ENEMY_UNIT_ID,
        channel_the_warp=False,
    )
    drift_payload = dict(cast(dict[str, JsonValue], drift_option.payload))
    drift_payload["target_rules_unit_instance_id"] = ENEMY_OTHER_ID
    invalid = drift_lifecycle.submit_decision(
        DecisionResult(
            result_id="phase17g-thousand-sons-payload-drift",
            request_id=drift_request.request_id,
            decision_type=drift_request.decision_type,
            actor_id=drift_request.actor_id,
            selected_option_id=drift_option.option_id,
            payload=validate_json_value(drift_payload),
        )
    )
    assert invalid.status_kind is LifecycleStatusKind.INVALID
    assert _require_state(drift_lifecycle).persisting_effects == []

    closed_lifecycle = _battle_ready_lifecycle(game_id="phase17g-thousand-sons-closed")
    closed_request = _next_cabal_request(closed_lifecycle)
    closed_state = _require_state(closed_lifecycle)
    closed_state.shooting_phase_state = ShootingPhaseState(
        battle_round=closed_state.battle_round,
        active_player_id="player-a",
    )
    closed_option = _ritual_option(
        closed_request,
        ritual_id=army_rule.CabalRitualId.DESTINYS_RUIN.value,
        target_rules_unit_id=ENEMY_UNIT_ID,
        channel_the_warp=False,
    )
    closed = closed_lifecycle.submit_decision(
        DecisionResult.for_request(
            result_id="phase17g-thousand-sons-window-closed",
            request=closed_request,
            selected_option_id=closed_option.option_id,
        )
    )
    assert closed.status_kind is LifecycleStatusKind.INVALID
    assert (
        cast(dict[str, JsonValue], closed.payload)["invalid_reason"]
        == "shooting_phase_start_window_closed"
    )
    assert closed_state.persisting_effects == []


def test_temporal_surge_requests_triggered_movement_and_forbids_charge() -> None:
    lifecycle = _battle_ready_lifecycle(game_id="phase17g-thousand-sons-temporal")
    request = _next_cabal_request(lifecycle)
    option = _ritual_option(
        request,
        ritual_id=army_rule.CabalRitualId.TEMPORAL_SURGE.value,
        target_rules_unit_id=FRIENDLY_TARGET_ID,
        channel_the_warp=False,
    )

    status = lifecycle.submit_decision(
        DecisionResult.for_request(
            result_id="phase17g-thousand-sons-temporal-result-False",
            request=request,
            selected_option_id=option.option_id,
        )
    )

    proposal_request = _movement_request_from_status(status)
    proposal = MovementProposalRequest.from_decision_request_payload(proposal_request.payload)
    assert proposal.decision_type == MOVEMENT_PROPOSAL_DECISION_TYPE
    assert proposal.unit_instance_id == FRIENDLY_TARGET_ID
    assert proposal.movement_phase_action == TRIGGERED_MOVEMENT_PROPOSAL_ACTION
    proposal_context = proposal.context
    assert proposal_context is not None
    assert proposal_context["context_kind"] == "triggered_movement"
    descriptor = cast(dict[str, JsonValue], proposal_context["descriptor"])
    assert descriptor["movement_kind"] == "triggered"
    assert descriptor["movement_mode"] == MovementMode.NORMAL.value

    witness = straight_line_witness_for_unit(
        lifecycle,
        unit_instance_id=FRIENDLY_TARGET_ID,
        dx=0.0,
        dy=1.0,
    )
    resolved = lifecycle.submit_decision(
        DecisionResult(
            result_id="phase17g-thousand-sons-temporal-move",
            request_id=proposal_request.request_id,
            decision_type=proposal_request.decision_type,
            actor_id=proposal_request.actor_id,
            selected_option_id=PARAMETERIZED_DECISION_OPTION_ID,
            payload=validate_json_value(
                MovementProposalPayload(
                    proposal_request_id=proposal.request_id,
                    proposal_kind=proposal.proposal_kind,
                    unit_instance_id=FRIENDLY_TARGET_ID,
                    movement_phase_action=TRIGGERED_MOVEMENT_PROPOSAL_ACTION,
                    witness=witness,
                ).to_payload()
            ),
        )
    )
    assert resolved.status_kind is not LifecycleStatusKind.INVALID
    state = _require_state(lifecycle)
    charge_effects = [
        effect
        for effect in state.persisting_effects_for_unit(FRIENDLY_TARGET_ID)
        if cast(dict[str, JsonValue], effect.effect_payload).get("charge_forbidden") is True
    ]
    assert len(charge_effects) == 1


def test_doombolt_excludes_lone_operatives_beyond_twelve_and_applies_wounds() -> None:
    lifecycle = _battle_ready_lifecycle(game_id="phase17g-thousand-sons-doombolt")
    request = _next_cabal_request(lifecycle)
    assert (
        _ritual_option_or_none(
            request,
            ritual_id=army_rule.CabalRitualId.DOOMBOLT.value,
            target_rules_unit_id=ENEMY_LONE_OPERATIVE_ID,
            channel_the_warp=False,
        )
        is None
    )
    option = _ritual_option(
        request,
        ritual_id=army_rule.CabalRitualId.DOOMBOLT.value,
        target_rules_unit_id=ENEMY_UNIT_ID,
        channel_the_warp=False,
    )
    before = _unit_remaining_wounds(_require_state(lifecycle), unit_instance_id=ENEMY_UNIT_ID)

    status = lifecycle.submit_decision(
        DecisionResult.for_request(
            result_id="phase17g-thousand-sons-doombolt-result",
            request=request,
            selected_option_id=option.option_id,
        )
    )

    assert status.status_kind is not LifecycleStatusKind.INVALID
    after = _unit_remaining_wounds(_require_state(lifecycle), unit_instance_id=ENEMY_UNIT_ID)
    assert after < before


def _battle_ready_lifecycle(*, game_id: str) -> GameLifecycle:
    config = _thousand_sons_config(game_id=game_id)
    lifecycle = GameLifecycle()
    lifecycle.start(config)
    state = _require_state(lifecycle)
    for army in _mustered_armies(config):
        state.record_army_definition(army)
    scenario = create_deterministic_battlefield_scenario(
        battlefield_id=f"{game_id}-battlefield",
        armies=tuple(state.army_definitions),
    )
    state.record_battlefield_state(scenario.battlefield_state)
    _place_unit(state, unit_instance_id=MANIFESTER_ID, x=10.0, y=10.0)
    _place_unit(state, unit_instance_id=FRIENDLY_TARGET_ID, x=10.0, y=15.0)
    _place_unit(state, unit_instance_id=ENEMY_UNIT_ID, x=24.0, y=10.0)
    _place_unit(state, unit_instance_id=ENEMY_OTHER_ID, x=24.0, y=15.0)
    _place_unit(state, unit_instance_id=ENEMY_LONE_OPERATIVE_ID, x=34.0, y=10.0)
    state.record_secondary_mission_choice(_fixed_secondary_choice(player_id="player-a"))
    state.record_secondary_mission_choice(_fixed_secondary_choice(player_id="player-b"))
    _complete_setup_through_gate(state=state, config=config)
    _set_current_battle_phase(state, BattlePhase.SHOOTING)
    _runtime_content_bundle(lifecycle)
    return lifecycle


def _thousand_sons_config(*, game_id: str) -> GameConfig:
    catalog = _thousand_sons_catalog()
    return GameConfig(
        game_id=game_id,
        allow_legacy_non_strict_rosters=True,
        ruleset_descriptor=RulesetDescriptor.warhammer_40000_eleventh_chapter_approved_2026_27(
            descriptor_version="core-v2-phase17g-thousand-sons-test",
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
                    faction_id=army_rule.THOUSAND_SONS_FACTION_ID,
                    detachment_ids=(THOUSAND_SONS_DETACHMENT_ID,),
                ),
                force_disposition_id="phase17g-thousand-sons-force",
                unit_selections=(
                    _unit_selection("rubric-marines", MANIFESTER_DATASHEET_ID),
                    _unit_selection("scarab-occult", FRIENDLY_TARGET_DATASHEET_ID),
                ),
            ),
            ArmyMusterRequest(
                army_id="army-beta",
                player_id="player-b",
                catalog_id=catalog.catalog_id,
                source_package_id=catalog.source_package_id,
                ruleset_id=catalog.ruleset_id,
                detachment_selection=DetachmentSelection(
                    faction_id="core-marine-force",
                    detachment_ids=(OPFOR_DETACHMENT_ID,),
                ),
                force_disposition_id="phase17g-thousand-sons-opfor",
                unit_selections=(
                    _unit_selection("enemy-unit", "core-intercessor-like-infantry"),
                    _unit_selection("enemy-unit-2", "core-intercessor-like-infantry"),
                    _unit_selection("lone-operative", ENEMY_LONE_OPERATIVE_DATASHEET_ID),
                ),
            ),
        ),
        player_ids=("player-a", "player-b"),
        turn_order=("player-a", "player-b"),
        fixed_secondary_mission_ids=("assassination", "bring_it_down"),
        mission_setup=_mission_setup(),
    )


def _thousand_sons_catalog() -> ArmyCatalog:
    base_catalog = ArmyCatalog.phase9a_canonical_content_pack()
    base_datasheet = base_catalog.datasheet_by_id("core-intercessor-like-infantry")
    return replace(
        base_catalog,
        datasheets=(
            *base_catalog.datasheets,
            _datasheet(
                base_datasheet,
                datasheet_id=MANIFESTER_DATASHEET_ID,
                name="Rubric Marines",
                keywords=("INFANTRY", "PSYKER"),
                faction_keywords=("THOUSAND SONS",),
                abilities=(_cabal_ability(),),
            ),
            _datasheet(
                base_datasheet,
                datasheet_id=FRIENDLY_TARGET_DATASHEET_ID,
                name="Scarab Occult Terminators",
                keywords=("INFANTRY",),
                faction_keywords=("THOUSAND SONS",),
                abilities=(),
            ),
            _datasheet(
                base_datasheet,
                datasheet_id=ENEMY_LONE_OPERATIVE_DATASHEET_ID,
                name="Enemy Lone Operative",
                keywords=("INFANTRY",),
                faction_keywords=("CORE Marines",),
                abilities=(_lone_operative_ability(),),
            ),
        ),
        factions=(
            *base_catalog.factions,
            FactionDefinition(
                faction_id=army_rule.THOUSAND_SONS_FACTION_ID,
                name="Thousand Sons",
                faction_keywords=("THOUSAND SONS",),
                source_ids=("phase17g:thousand-sons:faction",),
            ),
        ),
        detachments=(
            *base_catalog.detachments,
            DetachmentDefinition(
                detachment_id=THOUSAND_SONS_DETACHMENT_ID,
                name="Grand Coven",
                faction_id=army_rule.THOUSAND_SONS_FACTION_ID,
                detachment_point_cost=1,
                unit_datasheet_ids=(MANIFESTER_DATASHEET_ID, FRIENDLY_TARGET_DATASHEET_ID),
                force_disposition_ids=("phase17g-thousand-sons-force",),
                source_ids=("phase17g:thousand-sons:detachment:grand-coven",),
            ),
            DetachmentDefinition(
                detachment_id=OPFOR_DETACHMENT_ID,
                name="Opposing Force",
                faction_id="core-marine-force",
                detachment_point_cost=1,
                unit_datasheet_ids=(
                    "core-intercessor-like-infantry",
                    ENEMY_LONE_OPERATIVE_DATASHEET_ID,
                ),
                force_disposition_ids=("phase17g-thousand-sons-opfor",),
                source_ids=("phase17g:thousand-sons:detachment:opfor",),
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
    abilities: tuple[DatasheetAbilityDescriptor, ...],
) -> DatasheetDefinition:
    return replace(
        base_datasheet,
        datasheet_id=datasheet_id,
        name=name,
        keywords=DatasheetKeywordSet(
            keywords=keywords,
            faction_keywords=faction_keywords,
        ),
        abilities=abilities,
        source_ids=(f"phase17g:thousand-sons:datasheet:{datasheet_id}",),
    )


def _cabal_ability() -> DatasheetAbilityDescriptor:
    return DatasheetAbilityDescriptor(
        ability_id="phase17g-thousand-sons-cabal-of-sorcerers",
        name="Cabal of Sorcerers",
        source_id=army_rule.SOURCE_RULE_ID,
        support=CatalogAbilitySupport.DESCRIPTOR_ONLY,
        source_kind=CatalogAbilitySourceKind.DATASHEET,
        effect_description="thousand-sons-army-rule",
    )


def _lone_operative_ability() -> DatasheetAbilityDescriptor:
    return DatasheetAbilityDescriptor(
        ability_id="core-lone-operative",
        name="Lone Operative",
        source_id="core-rules:lone-operative",
        support=CatalogAbilitySupport.DESCRIPTOR_ONLY,
        source_kind=CatalogAbilitySourceKind.DATASHEET,
        effect_description="lone-operative",
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


def _place_unit(
    state: GameState,
    *,
    unit_instance_id: str,
    x: float,
    y: float,
) -> None:
    battlefield = state.battlefield_state
    if battlefield is None:
        raise AssertionError("battlefield is required")
    placement = battlefield.unit_placement_by_id(unit_instance_id)
    updated = placement.with_model_placements(
        tuple(
            model_placement.with_pose(Pose.at(x + (float(index) * 2.0), y, 0.0))
            for index, model_placement in enumerate(placement.model_placements)
        )
    )
    state.battlefield_state = battlefield.with_unit_placement(updated)


def _fixed_secondary_choice(*, player_id: str) -> SecondaryMissionChoice:
    return SecondaryMissionChoice(
        player_id=player_id,
        mode=SecondaryMissionMode.FIXED,
        fixed_mission_ids=("assassination", "bring_it_down"),
    )


def _complete_setup_through_gate(*, state: GameState, config: GameConfig) -> None:
    final_setup_step = state.setup_sequence[-1]
    while state.current_setup_step is not final_setup_step:
        state.complete_current_setup_step()
    SetupCompletionGate().complete_setup_and_enter_battle(
        state=state,
        decisions=DecisionController(),
        config=config,
    )


def _mission_setup() -> MissionSetup:
    return MissionSetup.from_mission_pack(
        mission_pack=chapter_approved_2026_27_mission_pack(),
        mission_pool_entry_id="mission-take-and-hold-vs-purge-the-foe-layout-3",
        terrain_layout_id="take-and-hold-vs-purge-the-foe-layout-3",
        attacker_player_id="player-a",
        defender_player_id="player-b",
    )


def _set_current_battle_phase(state: GameState, phase: BattlePhase) -> None:
    state.battle_phase_index = state.battle_phase_sequence.index(phase)


def _next_cabal_request(lifecycle: GameLifecycle) -> DecisionRequest:
    request = _request_from_status(lifecycle.advance_until_decision_or_terminal())
    if request is None:
        raise AssertionError("decision request is required")
    return request


def _request_from_status(status: LifecycleStatus) -> DecisionRequest | None:
    return status.decision_request


def _movement_request_from_status(status: LifecycleStatus) -> DecisionRequest:
    request = _request_from_status(status)
    if request is None:
        raise AssertionError("movement proposal request is required")
    if request.decision_type != MOVEMENT_PROPOSAL_DECISION_TYPE:
        raise AssertionError(f"unexpected decision type {request.decision_type}")
    return request


def _ritual_option(
    request: DecisionRequest,
    *,
    ritual_id: str,
    target_rules_unit_id: str,
    channel_the_warp: bool,
) -> DecisionOption:
    option = _ritual_option_or_none(
        request,
        ritual_id=ritual_id,
        target_rules_unit_id=target_rules_unit_id,
        channel_the_warp=channel_the_warp,
    )
    if option is None:
        raise AssertionError(f"missing Cabal option {ritual_id}->{target_rules_unit_id}")
    return option


def _ritual_option_or_none(
    request: DecisionRequest,
    *,
    ritual_id: str,
    target_rules_unit_id: str,
    channel_the_warp: bool,
) -> DecisionOption | None:
    for option in request.options:
        if option.option_id == army_rule.CABAL_DONE_OPTION_ID:
            continue
        payload = cast(dict[str, JsonValue], option.payload)
        if (
            payload["ritual_id"] == ritual_id
            and payload["target_rules_unit_instance_id"] == target_rules_unit_id
            and payload["channel_the_warp"] == channel_the_warp
        ):
            return option
    return None


def _done_option(request: DecisionRequest) -> DecisionOption:
    for option in request.options:
        if option.option_id == army_rule.CABAL_DONE_OPTION_ID:
            return option
    raise AssertionError("missing done option")


def _weapon_context(
    *,
    state: GameState,
    attacking_unit_instance_id: str,
    target_unit_instance_id: str,
    weapon_profile: WeaponProfile,
) -> WeaponProfileModifierContext:
    return WeaponProfileModifierContext(
        state=state,
        source_phase=BattlePhase.SHOOTING,
        attacking_unit_instance_id=attacking_unit_instance_id,
        attacker_model_instance_id=f"{attacking_unit_instance_id}:core-intercessor-like:001",
        target_unit_instance_id=target_unit_instance_id,
        weapon_profile=weapon_profile,
    )


def _ranged_weapon_profile() -> WeaponProfile:
    return WeaponProfile(
        profile_id="phase17g-thousand-sons-boltgun",
        name="Inferno Boltgun",
        range_profile=RangeProfile.distance(24),
        attack_profile=AttackProfile.fixed(2),
        skill=CharacteristicValue.from_raw(Characteristic.BALLISTIC_SKILL, 3),
        strength=CharacteristicValue.from_raw(Characteristic.STRENGTH, 4),
        armor_penetration=CharacteristicValue.from_raw(Characteristic.ARMOR_PENETRATION, 0),
        damage_profile=DamageProfile.fixed(1),
        source_ids=("phase17g:thousand-sons:test-ranged-weapon",),
    )


def _unit_remaining_wounds(state: GameState, *, unit_instance_id: str) -> int:
    army = state.army_definition_for_player("player-b")
    if army is None:
        raise AssertionError("enemy army is required")
    for unit in army.units:
        if unit.unit_instance_id == unit_instance_id:
            return sum(model.wounds_remaining for model in unit.own_models)
    raise AssertionError(f"missing unit {unit_instance_id}")


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
