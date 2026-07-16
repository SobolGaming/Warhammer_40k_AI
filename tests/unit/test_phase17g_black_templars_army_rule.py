from __future__ import annotations

import json
from collections.abc import Callable
from dataclasses import replace
from typing import cast

from warhammer40k_core.core.army_catalog import ArmyCatalog
from warhammer40k_core.core.attributes import Characteristic, CharacteristicValue
from warhammer40k_core.core.datasheet import DatasheetDefinition, DatasheetKeywordSet
from warhammer40k_core.core.detachment import DetachmentDefinition
from warhammer40k_core.core.faction import FactionDefinition
from warhammer40k_core.core.missions import ObjectiveMarkerDefinition
from warhammer40k_core.core.ruleset_descriptor import (
    BattlePhaseKind,
    MovementMode,
    RulesetDescriptor,
)
from warhammer40k_core.core.weapon_profiles import (
    AttackProfile,
    DamageProfile,
    RangeProfile,
    WeaponKeyword,
    WeaponProfile,
)
from warhammer40k_core.engine.army_mustering import ArmyDefinition, ArmyMusterRequest, muster_army
from warhammer40k_core.engine.battle_round_hooks import (
    SELECT_FACTION_RULE_BATTLE_ROUND_OPTION_DECISION_TYPE,
)
from warhammer40k_core.engine.battlefield_state import ModelPlacement, UnitPlacement
from warhammer40k_core.engine.charge_declaration_hooks import ChargeDeclarationContext
from warhammer40k_core.engine.decision_controller import DecisionController
from warhammer40k_core.engine.decision_result import DecisionResult
from warhammer40k_core.engine.effects import EffectExpiration, PersistingEffect
from warhammer40k_core.engine.faction_content.runtime import build_runtime_content_bundle
from warhammer40k_core.engine.faction_content.warhammer_40000_11th.black_templars import (
    army_rule,
)
from warhammer40k_core.engine.fall_back_hooks import FallBackEligibilityContext
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
    MovementProposalRequest,
    ProposalKind,
)
from warhammer40k_core.engine.phase import (
    BattlePhase,
    GameLifecycleStage,
)
from warhammer40k_core.engine.phases.charge import (
    CHARGE_MOVE_ACTION,
    CHARGE_MOVE_REQUIRED_TARGET_UNIT_INSTANCE_IDS_KEY,
    ChargeMoveProposal,
)
from warhammer40k_core.engine.placement import create_deterministic_battlefield_scenario
from warhammer40k_core.engine.runtime_modifiers import (
    RuntimeModifierRegistry,
    WeaponProfileModifierContext,
    WoundRollModifierContext,
)
from warhammer40k_core.engine.setup_completion import SetupCompletionGate
from warhammer40k_core.engine.source_backed_rerolls import (
    source_backed_reroll_permission_context_for_unit,
)
from warhammer40k_core.engine.sticky_objective_control import PhaseEndObjectiveControlContext
from warhammer40k_core.engine.target_restriction_hooks import ChargeTargetRestrictionContext
from warhammer40k_core.engine.unit_factory import UnitInstance
from warhammer40k_core.engine.wargear_selections import (
    ModelProfileSelection,
)
from warhammer40k_core.geometry.pose import Pose
from warhammer40k_core.rules.mission_pack_import import chapter_approved_2026_27_mission_pack

BLACK_TEMPLARS_UNIT_ID = "army-alpha:crusader-squad"
BLACK_TEMPLARS_DATASHEET_ID = "phase17g-black-templars-crusader-squad"
ENEMY_PSYKER_UNIT_ID = "army-beta:enemy-psyker"
ENEMY_PSYKER_DATASHEET_ID = "phase17g-black-templars-enemy-psyker"
ENEMY_NON_PSYKER_UNIT_ID = "army-beta:enemy-non-psyker"
ENEMY_NON_PSYKER_DATASHEET_ID = "phase17g-black-templars-enemy-non-psyker"


def test_runtime_bundle_loads_black_templars_vow_surfaces() -> None:
    bundle = build_runtime_content_bundle(_black_templars_config())
    summary = bundle.to_summary_payload()

    assert army_rule.HOOK_ID in summary["battle_round_start_hook_ids"]
    assert army_rule.ABHOR_CHARGE_DECLARATION_HOOK_ID in summary["charge_declaration_hook_ids"]
    assert (
        army_rule.ABHOR_CHARGE_TARGET_RESTRICTION_HOOK_ID
        in summary["charge_target_restriction_hook_ids"]
    )
    assert army_rule.SUFFER_FALL_BACK_ELIGIBILITY_HOOK_ID in summary["fall_back_hook_ids"]
    assert (
        army_rule.UPHOLD_OBJECTIVE_CONTROL_HOOK_ID
        in summary["phase_end_objective_control_hook_ids"]
    )
    assert army_rule.ABHOR_MELEE_PRECISION_MODIFIER_ID in summary["weapon_profile_modifier_ids"]
    assert army_rule.ACCEPT_ANY_CHALLENGE_WOUND_MODIFIER_ID in summary["wound_roll_modifier_ids"]


def test_lifecycle_requests_templar_vow_and_records_selected_vow() -> None:
    lifecycle = _battle_ready_lifecycle()
    contribution = army_rule.runtime_contribution()
    assert contribution.contribution_id == army_rule.CONTRIBUTION_ID
    assert not contribution.contribution_id.endswith(":scaffold")

    status = lifecycle.advance_until_decision_or_terminal()

    request = status.decision_request
    assert request is not None
    assert request.decision_type == SELECT_FACTION_RULE_BATTLE_ROUND_OPTION_DECISION_TYPE
    assert request.actor_id == "player-a"
    assert {option.option_id for option in request.options} == {
        "black_templars:templar_vows:abhor_the_witch",
        "black_templars:templar_vows:accept_any_challenge",
        "black_templars:templar_vows:suffer_not_the_unclean",
        "black_templars:templar_vows:uphold_the_honour",
    }

    lifecycle.submit_decision(
        DecisionResult.for_request(
            result_id="phase17g-black-templars-select-abhor",
            request=request,
            selected_option_id="black_templars:templar_vows:abhor_the_witch",
        )
    )

    state = _require_state(lifecycle)
    assert (
        army_rule.active_templar_vow_for_player(state, player_id="player-a")
        is army_rule.TemplarVow.ABHOR_THE_WITCH
    )
    restored = cast(GameStatePayload, json.loads(json.dumps(state.to_payload(), sort_keys=True)))
    assert restored == state.to_payload()


def test_abhor_adds_precision_to_melee_attacks_against_psykers_only() -> None:
    state = _black_templars_battle_state()
    _record_vow(state, army_rule.TemplarVow.ABHOR_THE_WITCH)

    modified = army_rule.abhor_weapon_profile_modifier(
        _weapon_profile_context(
            state=state,
            target_unit_id=ENEMY_PSYKER_UNIT_ID,
            source_phase=BattlePhase.FIGHT,
        )
    )
    non_psyker = army_rule.abhor_weapon_profile_modifier(
        _weapon_profile_context(
            state=state,
            target_unit_id=ENEMY_NON_PSYKER_UNIT_ID,
            source_phase=BattlePhase.FIGHT,
        )
    )
    shooting = army_rule.abhor_weapon_profile_modifier(
        _weapon_profile_context(
            state=state,
            target_unit_id=ENEMY_PSYKER_UNIT_ID,
            source_phase=BattlePhase.SHOOTING,
        )
    )

    assert WeaponKeyword.PRECISION in modified.keywords
    assert army_rule.SOURCE_RULE_ID in modified.source_ids
    assert WeaponKeyword.PRECISION not in non_psyker.keywords
    assert WeaponKeyword.PRECISION not in shooting.keywords


def test_accept_any_challenge_adds_melee_wound_bonus_when_strength_is_not_higher() -> None:
    state = _black_templars_battle_state()
    _record_vow(state, army_rule.TemplarVow.ACCEPT_ANY_CHALLENGE)

    assert (
        army_rule.accept_any_challenge_wound_roll_modifier(
            _wound_context(
                state=state,
                source_phase=BattlePhase.FIGHT,
                strength=4,
                toughness=4,
            )
        )
        == 1
    )
    assert (
        army_rule.accept_any_challenge_wound_roll_modifier(
            _wound_context(
                state=state,
                source_phase=BattlePhase.FIGHT,
                strength=5,
                toughness=4,
            )
        )
        == 0
    )
    assert (
        army_rule.accept_any_challenge_wound_roll_modifier(
            _wound_context(
                state=state,
                source_phase=BattlePhase.SHOOTING,
                strength=4,
                toughness=4,
            )
        )
        == 0
    )


def test_abhor_charge_grant_records_reroll_and_restricts_targets_to_psykers() -> None:
    state = _black_templars_battle_state(
        phase=BattlePhase.CHARGE,
        enemy_origins={
            "enemy-psyker": Pose.at(17.0, 20.0),
            "enemy-non-psyker": Pose.at(18.5, 20.0),
        },
    )
    _record_vow(state, army_rule.TemplarVow.ABHOR_THE_WITCH)

    grant = army_rule.abhor_charge_declaration_grant(
        ChargeDeclarationContext(
            state=state,
            player_id="player-a",
            battle_round=state.battle_round,
            unit_instance_id=BLACK_TEMPLARS_UNIT_ID,
            selection_request_id="phase17g-black-templars-charge-selection-request",
            selection_result_id="phase17g-black-templars-charge-selection-result",
        )
    )

    assert grant is not None
    assert grant.unit_effect_payload is not None
    state.record_persisting_effect(
        PersistingEffect(
            effect_id="phase17g-black-templars-abhor-charge-effect",
            source_rule_id=army_rule.SOURCE_RULE_ID,
            owner_player_id="player-a",
            target_unit_instance_ids=(BLACK_TEMPLARS_UNIT_ID,),
            started_battle_round=state.battle_round,
            started_phase=BattlePhaseKind.CHARGE,
            expiration=EffectExpiration.end_phase(
                battle_round=state.battle_round,
                phase=BattlePhaseKind.CHARGE,
                player_id="player-a",
            ),
            effect_payload=grant.unit_effect_payload,
        )
    )

    permission = source_backed_reroll_permission_context_for_unit(
        state=state,
        player_id="player-a",
        unit_instance_id=BLACK_TEMPLARS_UNIT_ID,
        roll_type="charge_roll",
        timing_window="after_charge_roll",
    )
    psyker_restriction = army_rule.abhor_charge_target_restriction(
        ChargeTargetRestrictionContext(
            state=state,
            player_id="player-a",
            battle_round=state.battle_round,
            charging_unit_instance_id=BLACK_TEMPLARS_UNIT_ID,
            target_unit_instance_id=ENEMY_PSYKER_UNIT_ID,
        )
    )
    non_psyker_restriction = army_rule.abhor_charge_target_restriction(
        ChargeTargetRestrictionContext(
            state=state,
            player_id="player-a",
            battle_round=state.battle_round,
            charging_unit_instance_id=BLACK_TEMPLARS_UNIT_ID,
            target_unit_instance_id=ENEMY_NON_PSYKER_UNIT_ID,
        )
    )

    assert permission is not None
    assert permission.source_payload["effect_kind"] == army_rule.ABHOR_CHARGE_EFFECT_KIND
    assert psyker_restriction is None
    assert non_psyker_restriction is not None
    assert (
        non_psyker_restriction.violation_code
        == "black_templars_abhor_charge_requires_psyker_target"
    )


def test_charge_move_rejects_no_move_when_required_psyker_target_is_reachable() -> None:
    request = MovementProposalRequest(
        request_id="phase17g-black-templars-charge-proposal",
        decision_type="submit_movement_proposal",
        actor_id="player-a",
        game_id="phase17g-black-templars-charge-proposal",
        battle_round=1,
        phase=BattlePhase.CHARGE.value,
        unit_instance_id=BLACK_TEMPLARS_UNIT_ID,
        proposal_kind=ProposalKind.CHARGE_MOVE,
        source_decision_request_id="phase17g-black-templars-charge-selection-request",
        source_decision_result_id="phase17g-black-templars-charge-selection-result",
        movement_phase_action=CHARGE_MOVE_ACTION,
        context={
            "movement_mode": MovementMode.CHARGE.value,
            "maximum_distance_inches": 7,
            "reachable_target_unit_instance_ids": [
                ENEMY_PSYKER_UNIT_ID,
                ENEMY_NON_PSYKER_UNIT_ID,
            ],
            "reachable_target_distances_inches": {
                ENEMY_PSYKER_UNIT_ID: 5.0,
                ENEMY_NON_PSYKER_UNIT_ID: 6.0,
            },
            CHARGE_MOVE_REQUIRED_TARGET_UNIT_INSTANCE_IDS_KEY: [ENEMY_PSYKER_UNIT_ID],
        },
    )
    proposal = ChargeMoveProposal(
        proposal_request_id=request.request_id,
        proposal_kind=ProposalKind.CHARGE_MOVE,
        unit_instance_id=BLACK_TEMPLARS_UNIT_ID,
        movement_phase_action=CHARGE_MOVE_ACTION,
        movement_mode=MovementMode.CHARGE,
        charge_target_unit_instance_ids=(),
    )

    result = proposal.validation_result_for_request(request)

    assert not result.is_valid
    assert result.violations[0].violation_code == "charge_required_target_not_selected"
    assert result.violations[0].field == "charge_target_unit_instance_ids"


def test_suffer_not_the_unclean_grants_charge_after_fall_back() -> None:
    state = _black_templars_battle_state(phase=BattlePhase.MOVEMENT)
    _record_vow(state, army_rule.TemplarVow.SUFFER_NOT_THE_UNCLEAN)

    grant = army_rule.suffer_not_the_unclean_fall_back_eligibility(
        FallBackEligibilityContext(
            state=state,
            player_id="player-a",
            battle_round=state.battle_round,
            unit_instance_id=BLACK_TEMPLARS_UNIT_ID,
            movement_request_id="phase17g-black-templars-fall-back-request",
            movement_result_id="phase17g-black-templars-fall-back-result",
        )
    )

    assert grant is not None
    assert grant.can_declare_charge is True
    assert grant.can_shoot is False


def test_uphold_the_honour_records_command_phase_sticky_control() -> None:
    state = _black_templars_battle_state()
    _place_black_templars_on_center_objective(state)
    _record_vow(state, army_rule.TemplarVow.UPHOLD_THE_HONOUR)

    states = army_rule.uphold_objective_control_states(
        PhaseEndObjectiveControlContext(
            state=state,
            event_log=DecisionController().event_log,
            completed_phase=BattlePhase.COMMAND,
            runtime_modifier_registry=RuntimeModifierRegistry.empty(),
        )
    )

    assert len(states) == 1
    assert states[0].player_id == "player-a"
    assert states[0].source_rule_id == army_rule.SOURCE_RULE_ID
    assert states[0].originating_unit_instance_id == BLACK_TEMPLARS_UNIT_ID
    assert states[0].replay_payload == {
        "effect_kind": army_rule.UPHOLD_STICKY_EFFECT_KIND,
        "selected_vow_id": army_rule.TemplarVow.UPHOLD_THE_HONOUR.value,
        "objective_id": states[0].objective_id,
        "originating_unit_instance_id": BLACK_TEMPLARS_UNIT_ID,
        "controlling_player_id": "player-a",
    }


def _battle_ready_lifecycle() -> GameLifecycle:
    config = _black_templars_config()
    lifecycle = GameLifecycle()
    lifecycle.start(config)
    state = _require_state(lifecycle)
    for army in _mustered_armies(config):
        state.record_army_definition(army)
    scenario = create_deterministic_battlefield_scenario(
        battlefield_id="phase17g-black-templars-lifecycle-battlefield",
        armies=tuple(state.army_definitions),
    )
    state.record_battlefield_state(scenario.battlefield_state)
    state.record_secondary_mission_choice(_fixed_secondary_choice(player_id="player-a"))
    state.record_secondary_mission_choice(_fixed_secondary_choice(player_id="player-b"))
    _complete_setup_through_gate(state=state, config=config)
    _runtime_content_bundle(lifecycle)
    return lifecycle


def _black_templars_battle_state(
    *,
    phase: BattlePhase = BattlePhase.COMMAND,
    enemy_origins: dict[str, Pose] | None = None,
) -> GameState:
    config = _black_templars_config(game_id=f"phase17g-black-templars-{phase.value}-state")
    armies = _mustered_armies(config)
    state = GameState.from_config(config)
    for army in armies:
        state.record_army_definition(army)
    scenario = create_deterministic_battlefield_scenario(
        battlefield_id=f"phase17g-black-templars-{phase.value}-battlefield",
        armies=armies,
    )
    battlefield = scenario.battlefield_state
    units = {
        unit.unit_instance_id.split(":", maxsplit=1)[1]: unit
        for army in armies
        for unit in army.units
    }
    resolved_enemy_origins = {} if enemy_origins is None else enemy_origins
    for key, unit in units.items():
        army_id = unit.unit_instance_id.split(":", maxsplit=1)[0]
        player_id = "player-a" if army_id == "army-alpha" else "player-b"
        if army_id == "army-alpha":
            poses = _compact_unit_poses(origin=Pose.at(10.0, 20.0), model_count=5)
        else:
            poses = _compact_unit_poses(
                origin=resolved_enemy_origins.get(key, Pose.at(40.0, 20.0)),
                model_count=5,
            )
        battlefield = battlefield.with_unit_placement(
            _unit_placement_at(unit, army_id=army_id, player_id=player_id, poses=poses)
        )
    state.record_battlefield_state(battlefield)
    state.record_secondary_mission_choice(_fixed_secondary_choice(player_id="player-a"))
    state.record_secondary_mission_choice(_fixed_secondary_choice(player_id="player-b"))
    state.stage = GameLifecycleStage.BATTLE
    state.setup_step_index = None
    state.battle_round = 1
    state.active_player_id = "player-a"
    state.battle_phase_index = state.battle_phase_sequence.index(phase)
    return state


def _black_templars_config(
    *,
    game_id: str = "phase17g-black-templars-lifecycle-game",
) -> GameConfig:
    catalog = _black_templars_lifecycle_catalog()
    return GameConfig(
        game_id=game_id,
        allow_legacy_non_strict_rosters=True,
        ruleset_descriptor=RulesetDescriptor.warhammer_40000_eleventh_chapter_approved_2026_27(
            descriptor_version="core-v2-phase17g-black-templars-test",
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
                    faction_id=army_rule.BLACK_TEMPLARS_FACTION_ID,
                    detachment_ids=("marshals-household",),
                ),
                force_disposition_id="phase17g-force",
                unit_selections=(_unit_selection("crusader-squad", BLACK_TEMPLARS_DATASHEET_ID),),
            ),
            ArmyMusterRequest(
                army_id="army-beta",
                player_id="player-b",
                catalog_id=catalog.catalog_id,
                source_package_id=catalog.source_package_id,
                ruleset_id=catalog.ruleset_id,
                detachment_selection=DetachmentSelection(
                    faction_id="core-marine-force",
                    detachment_ids=("phase17g-black-templars-enemy-force",),
                ),
                force_disposition_id="phase17g-force",
                unit_selections=(
                    _unit_selection("enemy-psyker", ENEMY_PSYKER_DATASHEET_ID),
                    _unit_selection("enemy-non-psyker", ENEMY_NON_PSYKER_DATASHEET_ID),
                ),
            ),
        ),
        player_ids=("player-a", "player-b"),
        turn_order=("player-a", "player-b"),
        fixed_secondary_mission_ids=("assassination", "bring_it_down"),
        mission_setup=_mission_setup(),
    )


def _black_templars_lifecycle_catalog() -> ArmyCatalog:
    base_catalog = ArmyCatalog.phase9a_canonical_content_pack()
    base_datasheet = base_catalog.datasheet_by_id("core-intercessor-like-infantry")
    return replace(
        base_catalog,
        datasheets=(
            *base_catalog.datasheets,
            _datasheet(
                base_datasheet,
                datasheet_id=BLACK_TEMPLARS_DATASHEET_ID,
                name="Primaris Crusader Squad",
                keywords=("Infantry", "Battleline"),
                faction_keywords=("Adeptus Astartes", "Black Templars"),
            ),
            _datasheet(
                base_datasheet,
                datasheet_id=ENEMY_PSYKER_DATASHEET_ID,
                name="Enemy Psyker",
                keywords=("Infantry", "Psyker"),
                faction_keywords=("CORE Marines",),
            ),
            _datasheet(
                base_datasheet,
                datasheet_id=ENEMY_NON_PSYKER_DATASHEET_ID,
                name="Enemy Infantry",
                keywords=("Infantry",),
                faction_keywords=("CORE Marines",),
            ),
        ),
        factions=(
            *base_catalog.factions,
            FactionDefinition(
                faction_id=army_rule.BLACK_TEMPLARS_FACTION_ID,
                name="Black Templars",
                faction_keywords=("Adeptus Astartes", "Black Templars"),
                source_ids=("phase17g:black-templars:faction",),
            ),
        ),
        detachments=(
            *base_catalog.detachments,
            DetachmentDefinition(
                detachment_id="marshals-household",
                name="Marshal's Household",
                faction_id=army_rule.BLACK_TEMPLARS_FACTION_ID,
                detachment_point_cost=1,
                unit_datasheet_ids=(BLACK_TEMPLARS_DATASHEET_ID,),
                force_disposition_ids=("phase17g-force",),
                source_ids=("phase17g:black-templars:detachment:marshals-household",),
            ),
            DetachmentDefinition(
                detachment_id="phase17g-black-templars-enemy-force",
                name="Black Templars Enemy Force",
                faction_id="core-marine-force",
                detachment_point_cost=1,
                unit_datasheet_ids=(
                    ENEMY_PSYKER_DATASHEET_ID,
                    ENEMY_NON_PSYKER_DATASHEET_ID,
                ),
                force_disposition_ids=("phase17g-force",),
                source_ids=("phase17g:black-templars:detachment:enemy-force",),
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
        source_ids=(f"phase17g:black-templars:datasheet:{datasheet_id}",),
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


def _record_vow(state: GameState, vow: army_rule.TemplarVow) -> None:
    state.record_persisting_effect(
        PersistingEffect(
            effect_id=f"phase17g-black-templars-vow:{vow.value}",
            source_rule_id=army_rule.SOURCE_RULE_ID,
            owner_player_id="player-a",
            target_unit_instance_ids=(BLACK_TEMPLARS_UNIT_ID,),
            started_battle_round=state.battle_round,
            started_phase=BattlePhaseKind.COMMAND,
            expiration=EffectExpiration.end_of_battle(),
            effect_payload={
                "effect_kind": army_rule.TEMPLAR_VOWS_EFFECT_KIND,
                "battle_round": state.battle_round,
                "phase": BattlePhase.COMMAND.value,
                "player_id": "player-a",
                "faction_id": army_rule.BLACK_TEMPLARS_FACTION_ID,
                "source_rule_id": army_rule.SOURCE_RULE_ID,
                "hook_id": army_rule.HOOK_ID,
                "selected_vow_id": vow.value,
                "selected_vow_label": "test vow",
                "selected_option_id": f"black_templars:templar_vows:{vow.value}",
                "request_id": "phase17g-black-templars-vow-request",
                "result_id": "phase17g-black-templars-vow-result",
            },
        )
    )


def _weapon_profile_context(
    *,
    state: GameState,
    target_unit_id: str,
    source_phase: BattlePhase,
) -> WeaponProfileModifierContext:
    return WeaponProfileModifierContext(
        state=state,
        source_phase=source_phase,
        attacking_unit_instance_id=BLACK_TEMPLARS_UNIT_ID,
        attacker_model_instance_id=f"{BLACK_TEMPLARS_UNIT_ID}:model-001",
        target_unit_instance_id=target_unit_id,
        weapon_profile=_weapon_profile(),
    )


def _wound_context(
    *,
    state: GameState,
    source_phase: BattlePhase,
    strength: int,
    toughness: int,
) -> WoundRollModifierContext:
    return WoundRollModifierContext(
        state=state,
        source_phase=source_phase,
        attacking_unit_instance_id=BLACK_TEMPLARS_UNIT_ID,
        attacker_model_instance_id=f"{BLACK_TEMPLARS_UNIT_ID}:model-001",
        target_unit_instance_id=ENEMY_NON_PSYKER_UNIT_ID,
        weapon_profile=_weapon_profile(),
        strength=strength,
        toughness=toughness,
    )


def _weapon_profile() -> WeaponProfile:
    return WeaponProfile(
        profile_id="phase17g-black-templars-chainsword",
        name="Astartes chainsword",
        range_profile=RangeProfile.melee(),
        attack_profile=AttackProfile.fixed(4),
        skill=CharacteristicValue.from_raw(Characteristic.WEAPON_SKILL, 3),
        strength=CharacteristicValue.from_raw(Characteristic.STRENGTH, 4),
        armor_penetration=CharacteristicValue.from_raw(Characteristic.ARMOR_PENETRATION, 1),
        damage_profile=DamageProfile.fixed(1),
        source_ids=("phase17g:black-templars:test-weapon",),
    )


def _place_black_templars_on_center_objective(state: GameState) -> None:
    if state.battlefield_state is None:
        raise AssertionError("test state requires battlefield_state")
    marker = _center_marker_definition(state)
    unit_placement = state.battlefield_state.unit_placement_by_id(BLACK_TEMPLARS_UNIT_ID)
    state.replace_battlefield_state(
        state.battlefield_state.with_unit_placement(
            _with_model_offsets(unit_placement, marker, offsets=((0.0, 0.0),))
        )
    )


def _center_marker_definition(state: GameState) -> ObjectiveMarkerDefinition:
    if state.mission_setup is None:
        raise AssertionError("test state requires mission setup")
    for marker in state.mission_setup.objective_markers:
        if marker.objective_marker_id.endswith(("-center", "-center-central")):
            return marker
    raise AssertionError("missing center objective marker")


def _with_model_offsets(
    unit_placement: UnitPlacement,
    marker: ObjectiveMarkerDefinition,
    *,
    offsets: tuple[tuple[float, float], ...],
) -> UnitPlacement:
    placements = list(unit_placement.model_placements)
    for index, (offset_x, offset_y) in enumerate(offsets):
        placement = placements[index]
        placements[index] = placement.with_pose(
            Pose.at(
                marker.x_inches + offset_x,
                marker.y_inches + offset_y,
                marker.z_inches,
                facing_degrees=placement.pose.facing.degrees,
            )
        )
    return unit_placement.with_model_placements(tuple(placements))


def _compact_unit_poses(*, origin: Pose, model_count: int) -> tuple[Pose, ...]:
    return tuple(
        Pose.at(
            origin.position.x + ((index % 5) * 1.4),
            origin.position.y + ((index // 5) * 1.4),
            origin.position.z,
            facing_degrees=origin.facing.degrees,
        )
        for index in range(model_count)
    )


def _unit_placement_at(
    unit: UnitInstance,
    *,
    army_id: str,
    player_id: str,
    poses: tuple[Pose, ...],
) -> UnitPlacement:
    return UnitPlacement(
        army_id=army_id,
        player_id=player_id,
        unit_instance_id=unit.unit_instance_id,
        model_placements=tuple(
            ModelPlacement(
                army_id=army_id,
                player_id=player_id,
                unit_instance_id=unit.unit_instance_id,
                model_instance_id=model.model_instance_id,
                pose=pose,
            )
            for model, pose in zip(unit.own_models, poses, strict=True)
        ),
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


def _fixed_secondary_choice(*, player_id: str) -> SecondaryMissionChoice:
    return SecondaryMissionChoice(
        player_id=player_id,
        mode=SecondaryMissionMode.FIXED,
        fixed_mission_ids=("assassination", "bring_it_down"),
    )


def _mission_setup() -> MissionSetup:
    return MissionSetup.from_mission_pack(
        mission_pack=chapter_approved_2026_27_mission_pack(),
        mission_pool_entry_id="mission-take-and-hold-vs-purge-the-foe-layout-3",
        terrain_layout_id="take-and-hold-vs-purge-the-foe-layout-3",
        attacker_player_id="player-a",
        defender_player_id="player-b",
    )


def _require_state(lifecycle: GameLifecycle) -> GameState:
    if lifecycle.state is None:
        raise AssertionError("lifecycle state is required")
    return lifecycle.state


def _runtime_content_bundle(lifecycle: GameLifecycle) -> object:
    require_runtime_content_bundle = cast(
        Callable[[], object],
        object.__getattribute__(lifecycle, "_require_runtime_content_bundle"),
    )
    return require_runtime_content_bundle()
