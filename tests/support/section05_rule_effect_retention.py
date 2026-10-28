# pyright: reportPrivateUsage=false
"""Exact retained RULE/FIGHT/REMOVED fixture closure from the catalog regression.

Constructed admitted battle state plus catalog-runtime installation; this fixture
does not establish normal pregame entry. Post-submission checkpoints are native.
"""

from __future__ import annotations

from dataclasses import replace
from typing import Any, cast

from tests.fight_end_fixture_helpers import single_fight_end_request
from tests.setup_completion_helpers import record_primary_turn_start_evidence_for_fixture
from tests.support.catalog_package_fixtures import (
    daemon_prince_unit,
    flesh_hounds_army,
    undivided_daemon_package,
)
from tests.support.catalog_runtime_fixtures import (
    battle_state_with_armies,
    datasheet_weapon_profile,
    single_model_unit_placement,
)

from warhammer40k_core.adapters.local_session import LocalGameSession
from warhammer40k_core.core.detachment import DetachmentDefinition
from warhammer40k_core.core.ruleset_descriptor import (
    BattlePhaseKind,
    FightPhaseStepKind,
    RulesetDescriptor,
)
from warhammer40k_core.core.weapon_profiles import WeaponProfile
from warhammer40k_core.engine import army_mustering
from warhammer40k_core.engine.abilities import (
    GENERIC_RULE_IR_ABILITY_HANDLER_ID,
    AbilityCatalogIndex,
    AbilityCatalogRecord,
    AbilityDefinition,
    AbilitySourceKind,
    AbilityTimingDescriptor,
)
from warhammer40k_core.engine.army_mustering import ArmyMusterRequest
from warhammer40k_core.engine.battle_round_flow import BattleRoundFlow
from warhammer40k_core.engine.battlefield_state import BattlefieldRuntimeState, PlacedArmy
from warhammer40k_core.engine.catalog_selected_to_fight_risk_runtime import (
    CatalogSelectedToFightRiskRuntime,
)
from warhammer40k_core.engine.damage_allocation import (
    DECLINE_DESTRUCTION_REACTION_OPTION_ID,
    DestructionReactionKind,
    DestructionReactionSource,
    FeelNoPainSource,
)
from warhammer40k_core.engine.decision_controller import DecisionController
from warhammer40k_core.engine.decision_request import DecisionRequest
from warhammer40k_core.engine.decision_result import DecisionResult
from warhammer40k_core.engine.effects import EffectExpiration, PersistingEffect
from warhammer40k_core.engine.event_log import validate_json_value
from warhammer40k_core.engine.fight_order import FightPhaseState
from warhammer40k_core.engine.fight_phase_end_hooks import (
    FightPhaseEndHookRegistry,
    FightPhaseEndRequestContext,
    FightPhaseEndResultContext,
)
from warhammer40k_core.engine.fight_unit_selected_hooks import (
    FightUnitSelectedContext,
    FightUnitSelectedGrantRegistry,
)
from warhammer40k_core.engine.fights_first import FightsFirstRegistry
from warhammer40k_core.engine.game_state import (
    GameConfig,
    GameState,
    SecondaryMissionChoice,
    SecondaryMissionMode,
)
from warhammer40k_core.engine.lifecycle import GameLifecycle
from warhammer40k_core.engine.list_validation import UnitMusterSelection
from warhammer40k_core.engine.phase import BattlePhase
from warhammer40k_core.engine.phases.charge import ChargePhaseHandler
from warhammer40k_core.engine.phases.fight import FightPhaseHandler
from warhammer40k_core.engine.phases.movement import MovementPhaseHandler
from warhammer40k_core.engine.phases.shooting import ShootingPhaseHandler
from warhammer40k_core.engine.reaction_queue import ReactionQueue
from warhammer40k_core.engine.timing_windows import TimingTriggerKind
from warhammer40k_core.engine.unit_factory import UnitInstance
from warhammer40k_core.engine.wargear_selections import ModelProfileSelection
from warhammer40k_core.rules.objective_terminology import ObjectiveRuleScope
from warhammer40k_core.rules.rule_compiler import compile_rule_source_text
from warhammer40k_core.rules.source_data import RuleSourceText


def _pending_daemonic_patrons_fight_on_death_fixture(
    *, cleanup_fnp: bool = False
) -> tuple[
    GameState,
    DecisionController,
    CatalogSelectedToFightRiskRuntime,
    UnitInstance,
    str,
    str,
    str,
]:
    state, _runtime, source, enemy, _profile = _daemonic_patrons_runtime_fixture(enemy_x=30.0)
    # The first mandatory liability belongs to the active player under 01.03.
    state.active_player_id = "player-enemy"
    assert state.fight_phase_state is not None
    state.fight_phase_state = replace(state.fight_phase_state, active_player_id="player-enemy")
    runtime = CatalogSelectedToFightRiskRuntime(
        {
            "player-source": AbilityCatalogIndex.from_records(
                _daemonic_patrons_records(source=source)
            ),
            "player-enemy": AbilityCatalogIndex.from_records(
                _daemonic_patrons_records(source=enemy)
            ),
        },
        tuple(state.army_definitions),
    )
    decisions = DecisionController()
    for player_id in state.player_ids:
        state.record_secondary_mission_choice(
            SecondaryMissionChoice(
                player_id=player_id,
                mode=SecondaryMissionMode.FIXED,
                fixed_mission_ids=("assassination", "bring_it_down"),
            )
        )
    record_primary_turn_start_evidence_for_fixture(state, decisions=decisions)
    if not cleanup_fnp:
        _record_daemonic_patrons_effect(state=state, runtime=runtime, source=source)
    _record_daemonic_patrons_effect(
        state=state,
        runtime=runtime,
        source=enemy,
        owner_player_id="player-enemy",
        effect_id="daemonic-patrons-next-liability-effect",
    )
    model_id = enemy.own_models[0].model_instance_id
    reaction_source = DestructionReactionSource(
        source_id="test:daemonic-patrons:fight-on-death:end-interrupt",
        reaction_kind=DestructionReactionKind.FIGHT_ON_DEATH,
        source_rule_id="test:daemonic-patrons:fight-on-death:end-interrupt",
    )
    state.clear_model_destruction_reaction_sources(model_instance_id=model_id)
    state.record_model_destruction_reaction_sources(
        model_instance_id=model_id,
        sources=(
            reaction_source,
            *(
                (
                    DestructionReactionSource(
                        source_id="order-30-rule-dd",
                        source_rule_id="order-30-rule-dd",
                        reaction_kind=DestructionReactionKind.DEADLY_DEMISE,
                        optional=False,
                        payload={
                            "trigger_roll_threshold": 1,
                            "range_inches": 40.0,
                            "mortal_wounds": {"kind": "fixed", "value": 1},
                        },
                    ),
                )
                if cleanup_fnp
                else ()
            ),
        ),
    )
    if cleanup_fnp:
        state.record_model_feel_no_pain_sources(
            model_instance_id=source.own_models[0].model_instance_id,
            decline_allowed=True,
            sources=(FeelNoPainSource(source_id="order-30-rule-fnp", threshold=6),),
        )
    request = single_fight_end_request(
        FightPhaseEndHookRegistry.from_bindings(runtime.fight_phase_end_hook_bindings()),
        FightPhaseEndRequestContext(state=state, decisions=decisions),
    )
    assert isinstance(request, DecisionRequest)
    assert request.actor_id == "player-enemy"
    decisions.request_decision(request)
    destruction_record = decisions.submit_result(
        DecisionResult.for_request(
            result_id="daemonic-patrons-fight-on-death-destruction",
            request=request,
            selected_option_id=request.options[0].option_id,
        )
    )
    status = runtime.apply_fight_phase_end_result(
        FightPhaseEndResultContext(
            state=state,
            decisions=decisions,
            request=destruction_record.request,
            result=destruction_record.result,
        )
    )
    assert type(status) is not bool
    reaction_request = decisions.queue.peek_next()
    reaction_option = next(
        option
        for option in reaction_request.options
        if option.option_id != DECLINE_DESTRUCTION_REACTION_OPTION_ID
    )
    return (
        state,
        decisions,
        runtime,
        source,
        model_id,
        reaction_request.request_id,
        reaction_option.option_id,
    )


def _daemonic_patrons_session(
    *,
    state: GameState,
    decisions: DecisionController,
) -> tuple[LocalGameSession, GameConfig]:
    package = undivided_daemon_package()
    fixture_catalog = replace(
        package.army_catalog,
        detachments=(
            DetachmentDefinition(
                canonical_detachment_id="phase17k-daemons",
                detachment_id="phase17k-daemons",
                name="Phase 17K Daemons",
                faction_id=package.army_catalog.factions[0].faction_id,
                detachment_point_cost=1,
                unit_datasheet_ids=("000001149",),
                force_disposition_ids=("take-and-hold", "purge-the-foe"),
                source_ids=("test:phase17k-daemons",),
            ),
        ),
    )
    resume_config = GameConfig(
        game_id=state.game_id,
        ruleset_descriptor=RulesetDescriptor.warhammer_40000_eleventh(),
        army_catalog=fixture_catalog,
        army_muster_requests=tuple(
            ArmyMusterRequest(
                army_id=army.army_id,
                player_id=army.player_id,
                catalog_id=army.catalog_id,
                source_package_id=army.source_package_id,
                ruleset_id=army.ruleset_id,
                detachment_selection=army.detachment_selection,
                force_disposition_id=army.force_disposition_id,
                unit_selections=tuple(
                    UnitMusterSelection(
                        unit_selection_id=unit.unit_instance_id.removeprefix(f"{army.army_id}:"),
                        datasheet_id=unit.datasheet_id,
                        model_profile_selections=(
                            ModelProfileSelection(
                                model_profile_id=unit.own_models[0].model_profile_id,
                                model_count=len(unit.own_models),
                            ),
                        ),
                        wargear_selections=unit.wargear_selections,
                        mustering_option_selections=unit.mustering_option_selections,
                    )
                    for unit in army.units
                ),
            )
            for army in state.army_definitions
        ),
        player_ids=state.player_ids,
        turn_order=state.turn_order,
        fixed_secondary_mission_ids=("assassination", "bring_it_down"),
        mission_setup=state.mission_setup,
        allow_legacy_non_strict_rosters=True,
        model_geometries=package.model_geometries,
    )
    # Match the canonical catalog's roster diagnostics as well as its units.
    for muster_request in resume_config.army_muster_requests:
        expected = army_mustering.muster_army(
            catalog=fixture_catalog,
            request=muster_request,
            model_geometries=package.model_geometries,
        )
        state.replace_army_definitions(
            [
                replace(army, roster_legality_report=expected.roster_legality_report)
                if army.army_id == expected.army_id
                else army
                for army in state.army_definitions
            ]
        )
    session = LocalGameSession(
        lifecycle=GameLifecycle.from_payload(
            cast(
                Any,
                {
                    "config": None,
                    "parameterized_movement_proposals": True,
                    "state": state.to_payload(),
                    "decisions": decisions.to_payload(),
                    "reaction_queue": ReactionQueue().to_payload(),
                },
            )
        )
    )
    return session, resume_config


def _install_daemonic_patrons_resume_runtime(
    *,
    session: LocalGameSession,
    config: GameConfig,
    runtime: CatalogSelectedToFightRiskRuntime,
) -> None:
    fight_handler = FightPhaseHandler(
        ruleset_descriptor=config.ruleset_descriptor,
        army_catalog=config.army_catalog,
        fight_phase_end_hooks=FightPhaseEndHookRegistry.from_bindings(
            runtime.fight_phase_end_hook_bindings()
        ),
    )
    session.lifecycle._config = config
    session.lifecycle._refresh_runtime_content_bundle_if_armies_mustered()
    session.lifecycle._fight_phase_handler = fight_handler
    session.lifecycle._movement_phase_handler = MovementPhaseHandler(
        ruleset_descriptor=config.ruleset_descriptor,
        army_catalog=config.army_catalog,
    )
    session.lifecycle._shooting_phase_handler = ShootingPhaseHandler(
        ruleset_descriptor=config.ruleset_descriptor,
        army_catalog=config.army_catalog,
    )
    session.lifecycle._charge_phase_handler = ChargePhaseHandler(
        ruleset_descriptor=config.ruleset_descriptor,
    )
    from warhammer40k_core.engine.fight_phase_end_sequencing import fight_end_boundary_binding
    from warhammer40k_core.engine.turn_end_hooks import TurnEndHookRegistry

    session.lifecycle._battle_round_flow = BattleRoundFlow(
        phase_handlers=session.lifecycle._phase_handlers(),
        turn_end_hooks=TurnEndHookRegistry.from_bindings(
            (fight_end_boundary_binding(fight_handler.fight_phase_end_hooks),)
        ),
        ruleset_descriptor=config.ruleset_descriptor,
        army_catalog=config.army_catalog,
    )


def _daemonic_patrons_runtime_fixture(
    *, enemy_x: float = 14.0
) -> tuple[
    GameState,
    CatalogSelectedToFightRiskRuntime,
    UnitInstance,
    UnitInstance,
    WeaponProfile,
]:
    package = undivided_daemon_package()
    source = daemon_prince_unit(
        package=package,
        datasheet_id="000001149",
        allegiance="SLAANESH",
        unit_selection_id="daemonic-patrons-source",
        army_id="army-source",
    )
    enemy = daemon_prince_unit(
        package=package,
        datasheet_id="000001149",
        allegiance="KHORNE",
        unit_selection_id="daemonic-patrons-enemy",
        army_id="army-enemy",
    )
    source_army = flesh_hounds_army(
        package=package,
        unit=source,
        player_id="player-source",
        army_id="army-source",
        force_disposition_id="take-and-hold",
    )
    enemy_army = flesh_hounds_army(
        package=package,
        unit=enemy,
        player_id="player-enemy",
        army_id="army-enemy",
        force_disposition_id="purge-the-foe",
    )
    battlefield = BattlefieldRuntimeState(
        battlefield_id="daemonic-patrons-battlefield",
        battlefield_width_inches=60.0,
        battlefield_depth_inches=44.0,
        placed_armies=(
            PlacedArmy(
                army_id=source_army.army_id,
                player_id=source_army.player_id,
                unit_placements=(single_model_unit_placement(source_army, source, x=12.0),),
            ),
            PlacedArmy(
                army_id=enemy_army.army_id,
                player_id=enemy_army.player_id,
                unit_placements=(single_model_unit_placement(enemy_army, enemy, x=enemy_x),),
            ),
        ),
    )
    state = battle_state_with_armies(
        armies=(source_army, enemy_army),
        battlefield=battlefield,
        active_player_id=source_army.player_id,
        phase=BattlePhase.FIGHT,
    )
    policy = state.runtime_ruleset_descriptor().fight_policy
    state.fight_phase_state = FightPhaseState.start(
        battle_round=1,
        active_player_id=source_army.player_id,
        policy=policy,
        engaged_at_fight_step_start_unit_ids=(),
        fights_first_registry=FightsFirstRegistry(),
    ).with_current_step(current_step=FightPhaseStepKind.END, policy=policy)
    records = _daemonic_patrons_records(source=source)
    runtime = CatalogSelectedToFightRiskRuntime(
        {
            source_army.player_id: AbilityCatalogIndex.from_records(records),
            enemy_army.player_id: AbilityCatalogIndex.from_records(()),
        },
        (source_army, enemy_army),
    )
    profile = datasheet_weapon_profile(
        package.army_catalog,
        datasheet_id=source.datasheet_id,
        profile_name="Hellforged weapons - strike",
    )
    return state, runtime, source, enemy, profile


def _record_daemonic_patrons_effect(
    *,
    state: GameState,
    runtime: CatalogSelectedToFightRiskRuntime,
    source: UnitInstance,
    owner_player_id: str = "player-source",
    effect_id: str = "daemonic-patrons-kill-effect",
) -> None:
    active_player_id = state.active_player_id
    assert active_player_id is not None
    grants = FightUnitSelectedGrantRegistry.from_bindings(
        runtime.fight_unit_selected_grant_bindings()
    ).grants_for(
        FightUnitSelectedContext(
            state=state,
            player_id=owner_player_id,
            battle_round=1,
            unit_instance_id=source.unit_instance_id,
            fight_type="normal",
            ordering_band="remaining_combats",
            request_id="daemonic-patrons-kill-activation-request",
            result_id="daemonic-patrons-kill-activation-result",
        )
    )
    state.record_persisting_effect(
        PersistingEffect(
            effect_id=effect_id,
            source_rule_id=grants[0].source_id,
            owner_player_id=owner_player_id,
            target_unit_instance_ids=(source.unit_instance_id,),
            started_battle_round=1,
            started_phase=BattlePhaseKind.FIGHT,
            expiration=EffectExpiration.end_phase(
                battle_round=1,
                phase=BattlePhaseKind.FIGHT,
                player_id=active_player_id,
            ),
            effect_payload=grants[0].timed_effects[0].effect_payload,
        )
    )


def _daemonic_patrons_records(*, source: UnitInstance) -> tuple[AbilityCatalogRecord, ...]:
    source_text = RuleSourceText.from_raw(
        objective_scope=ObjectiveRuleScope.CORE_RULES,
        source_id="test:emperors-children:daemonic-patrons",
        raw_text=(
            "Each time this unit is selected to fight, it can call upon daemonic patrons. "
            "If it does, until the end of the phase, each time a model in this unit makes "
            "an attack, an unmodified Wound roll of 3+ scores a Critical Wound. At the end "
            "of the Fight phase, if this unit called upon daemonic patrons this phase and "
            "no enemy models were destroyed by attacks made by models in this unit this "
            "phase, one model in this unit is destroyed."
        ),
    )
    rule_ir = compile_rule_source_text(
        source_text,
        source_keyword_sequence_parts=("FLAWLESS BLADES",),
    ).rule_ir
    records: list[AbilityCatalogRecord] = []
    for index, clause in enumerate(rule_ir.clauses, start=1):
        trigger_kind = (
            TimingTriggerKind.JUST_AFTER_FRIENDLY_UNIT_SELECTED_TO_FIGHT
            if index == 1
            else TimingTriggerKind.END_PHASE
        )
        records.append(
            AbilityCatalogRecord(
                record_id=f"record:daemonic-patrons:{index}",
                definition=AbilityDefinition(
                    ability_id=f"ability:daemonic-patrons:{index}",
                    name="Daemonic Patrons",
                    source_id=source_text.source_id,
                    when_descriptor="Selected to fight or end of Fight phase.",
                    effect_descriptor="Critical Wounds with a failed-activation consequence.",
                    restrictions_descriptor="Source-backed Daemonic Patrons RuleIR.",
                    timing=AbilityTimingDescriptor(
                        trigger_kind=trigger_kind,
                        phase=BattlePhaseKind.FIGHT,
                    ),
                    handler_id=GENERIC_RULE_IR_ABILITY_HANDLER_ID,
                    replay_payload=validate_json_value(
                        {
                            "rule_ir": rule_ir.to_payload(),
                            "runtime_clause_id": clause.clause_id,
                        }
                    ),
                ),
                source_kind=AbilitySourceKind.DATASHEET,
                datasheet_id=source.datasheet_id,
            )
        )
    return tuple(records)


__all__ = (
    "_daemonic_patrons_session",
    "_install_daemonic_patrons_resume_runtime",
    "_pending_daemonic_patrons_fight_on_death_fixture",
)
