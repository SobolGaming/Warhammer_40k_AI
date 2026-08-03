from __future__ import annotations

from dataclasses import replace

from tests.support.catalog_package_fixtures import (
    daemon_prince_unit,
    flesh_hounds_army,
    undivided_daemon_package,
)
from tests.support.catalog_runtime_fixtures import (
    battle_state_with_armies,
    single_model_unit_placement,
)

from warhammer40k_core.core.ruleset_descriptor import BattlePhaseKind, FightPhaseStepKind
from warhammer40k_core.engine.abilities import (
    GENERIC_RULE_IR_ABILITY_HANDLER_ID,
    AbilityCatalogIndex,
    AbilityCatalogRecord,
    AbilityDefinition,
    AbilitySourceKind,
    AbilityTimingDescriptor,
)
from warhammer40k_core.engine.attached_unit_formation import AttachedUnitFormation
from warhammer40k_core.engine.battlefield_state import BattlefieldRuntimeState, PlacedArmy
from warhammer40k_core.engine.catalog_selected_to_fight_risk_runtime import (
    CatalogSelectedToFightRiskRuntime,
)
from warhammer40k_core.engine.decision_controller import DecisionController
from warhammer40k_core.engine.effects import EffectExpiration, PersistingEffect
from warhammer40k_core.engine.event_log import validate_json_value
from warhammer40k_core.engine.fight_order import FightPhaseState
from warhammer40k_core.engine.fight_unit_selected_hooks import (
    FightUnitSelectedContext,
    FightUnitSelectedGrantRegistry,
)
from warhammer40k_core.engine.fights_first import FightsFirstRegistry
from warhammer40k_core.engine.game_state import GameState
from warhammer40k_core.engine.phase import BattlePhase
from warhammer40k_core.engine.timing_windows import TimingTriggerKind
from warhammer40k_core.engine.unit_factory import UnitInstance
from warhammer40k_core.rules.rule_compiler import compile_rule_source_text
from warhammer40k_core.rules.source_data import RuleSourceText


def attached_selected_to_fight_risk_fixture() -> tuple[
    GameState,
    CatalogSelectedToFightRiskRuntime,
    DecisionController,
    UnitInstance,
    UnitInstance,
    UnitInstance,
    str,
]:
    package = undivided_daemon_package()
    bodyguard = daemon_prince_unit(
        package=package,
        datasheet_id="000001149",
        allegiance="SLAANESH",
        unit_selection_id="risk-bodyguard",
        army_id="army-source",
    )
    leader = daemon_prince_unit(
        package=package,
        datasheet_id="000001149",
        allegiance="SLAANESH",
        unit_selection_id="risk-leader",
        army_id="army-source",
    )
    enemy = daemon_prince_unit(
        package=package,
        datasheet_id="000001149",
        allegiance="KHORNE",
        unit_selection_id="risk-enemy",
        army_id="army-enemy",
    )
    attached_id = "attached-unit:army-source:risk-formation"
    formation = AttachedUnitFormation(
        attached_unit_instance_id=attached_id,
        bodyguard_unit_instance_id=bodyguard.unit_instance_id,
        leader_unit_instance_ids=(leader.unit_instance_id,),
        component_unit_instance_ids=tuple(
            sorted((bodyguard.unit_instance_id, leader.unit_instance_id))
        ),
        source_id="test:risk-formation",
        attachment_source_ids=("test:risk-formation:eligibility",),
    )
    source_army = replace(
        flesh_hounds_army(
            package=package,
            unit=bodyguard,
            player_id="player-source",
            army_id="army-source",
        ),
        units=(bodyguard, leader),
        attached_units=(formation,),
    )
    enemy_army = flesh_hounds_army(
        package=package,
        unit=enemy,
        player_id="player-enemy",
        army_id="army-enemy",
    )
    battlefield = BattlefieldRuntimeState(
        battlefield_id="attached-risk-battlefield",
        battlefield_width_inches=60.0,
        battlefield_depth_inches=44.0,
        placed_armies=(
            PlacedArmy(
                army_id=source_army.army_id,
                player_id=source_army.player_id,
                unit_placements=(
                    single_model_unit_placement(source_army, bodyguard, x=12.0),
                    single_model_unit_placement(source_army, leader, x=13.0),
                ),
            ),
            PlacedArmy(
                army_id=enemy_army.army_id,
                player_id=enemy_army.player_id,
                unit_placements=(single_model_unit_placement(enemy_army, enemy, x=16.0),),
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
    records = _selected_to_fight_risk_records(datasheet_id=bodyguard.datasheet_id)
    runtime = CatalogSelectedToFightRiskRuntime(
        {
            source_army.player_id: AbilityCatalogIndex.from_records(records),
            enemy_army.player_id: AbilityCatalogIndex.from_records(()),
        },
        (source_army, enemy_army),
    )
    grants = FightUnitSelectedGrantRegistry.from_bindings(
        runtime.fight_unit_selected_grant_bindings()
    ).grants_for(
        FightUnitSelectedContext(
            state=state,
            player_id=source_army.player_id,
            battle_round=1,
            unit_instance_id=attached_id,
            fight_type="normal",
            ordering_band="remaining_combats",
            request_id="attached-risk-request",
            result_id="attached-risk-result",
        )
    )
    for suffix in ("first", "repeat"):
        state.record_persisting_effect(
            PersistingEffect(
                effect_id=f"attached-risk-effect:{suffix}",
                source_rule_id=grants[0].source_id,
                owner_player_id=source_army.player_id,
                target_unit_instance_ids=(attached_id,),
                started_battle_round=1,
                started_phase=BattlePhaseKind.FIGHT,
                expiration=EffectExpiration.end_phase(
                    battle_round=1,
                    phase=BattlePhaseKind.FIGHT,
                    player_id=source_army.player_id,
                ),
                effect_payload=grants[0].unit_effect_payload,
            )
        )
    decisions = DecisionController()
    state.recover_starting_strength_after_attached_unit_split(
        player_id=source_army.player_id,
        attached_unit_instance_id=attached_id,
        surviving_unit_instance_ids=(bodyguard.unit_instance_id, leader.unit_instance_id),
        event_log=decisions.event_log,
    )
    for model in (*bodyguard.own_models, *leader.own_models):
        state.clear_model_destruction_reaction_sources(model_instance_id=model.model_instance_id)
    return state, runtime, decisions, bodyguard, leader, enemy, attached_id


def _selected_to_fight_risk_records(*, datasheet_id: str) -> tuple[AbilityCatalogRecord, ...]:
    source_text = RuleSourceText.from_raw(
        source_id="test:emperors-children:attached-daemonic-patrons",
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
        source_text, source_keyword_sequence_parts=("FLAWLESS BLADES",)
    ).rule_ir
    return tuple(
        AbilityCatalogRecord(
            record_id=f"record:attached-daemonic-patrons:{index}",
            definition=AbilityDefinition(
                ability_id=f"ability:attached-daemonic-patrons:{index}",
                name="Daemonic Patrons",
                source_id=source_text.source_id,
                when_descriptor="Selected to fight or end of Fight phase.",
                effect_descriptor="Critical Wounds with a failed-activation consequence.",
                restrictions_descriptor="Source-backed Daemonic Patrons RuleIR.",
                timing=AbilityTimingDescriptor(
                    trigger_kind=(
                        TimingTriggerKind.JUST_AFTER_FRIENDLY_UNIT_SELECTED_TO_FIGHT
                        if index == 1
                        else TimingTriggerKind.END_PHASE
                    ),
                    phase=BattlePhaseKind.FIGHT,
                ),
                handler_id=GENERIC_RULE_IR_ABILITY_HANDLER_ID,
                replay_payload=validate_json_value(
                    {"rule_ir": rule_ir.to_payload(), "runtime_clause_id": clause.clause_id}
                ),
            ),
            source_kind=AbilitySourceKind.DATASHEET,
            datasheet_id=datasheet_id,
        )
        for index, clause in enumerate(rule_ir.clauses, start=1)
    )
