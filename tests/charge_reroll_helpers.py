from __future__ import annotations

from dataclasses import replace
from typing import cast

from tests.phase15a_charge_declaration_helpers import charge_lifecycle, compact_test_unit_poses
from warhammer40k_core.adapters.local_session import LocalGameSession
from warhammer40k_core.core.army_catalog import ArmyCatalog
from warhammer40k_core.core.datasheet import (
    CatalogAbilitySourceKind,
    CatalogAbilitySupport,
    CatalogJsonObject,
    DatasheetAbilityDescriptor,
)
from warhammer40k_core.engine.charge_phase_state import ChargePhaseState
from warhammer40k_core.engine.command_points import CommandPointSourceKind
from warhammer40k_core.engine.effects import EffectExpiration, PersistingEffect
from warhammer40k_core.engine.phase import BattlePhase
from warhammer40k_core.geometry.pose import Pose
from warhammer40k_core.rules.objective_terminology import ObjectiveRuleScope
from warhammer40k_core.rules.rule_compiler import compile_rule_source_text
from warhammer40k_core.rules.source_data import RuleSourceText


def reroll_catalog() -> ArmyCatalog:
    base = ArmyCatalog.phase9a_canonical_content_pack()
    sheet = base.datasheet_by_id("core-intercessor-like-infantry")
    source = RuleSourceText.from_raw(
        source_id="test:order49:natural-charge-reroll",
        raw_text="You can re-roll Charge rolls made for this unit.",
        objective_scope=ObjectiveRuleScope.CORE_RULES,
    )
    ir = compile_rule_source_text(source, source_keyword_sequence_parts=("INFANTRY",)).rule_ir
    ability = DatasheetAbilityDescriptor(
        ability_id="order49-natural-charge-reroll",
        name="Natural Charge reroll fixture",
        source_id=source.source_id,
        support=CatalogAbilitySupport.GENERIC_RULE_IR,
        source_kind=CatalogAbilitySourceKind.DATASHEET,
        effect_description=source.raw_text,
        rule_ir_payload=cast(CatalogJsonObject, ir.to_payload()),
    )
    return replace(
        base,
        datasheets=tuple(
            replace(s, abilities=(*s.abilities, ability))
            if s.datasheet_id == sheet.datasheet_id
            else s
            for s in base.datasheets
        ),
    )


def heroic_session(*, natural: bool) -> tuple[LocalGameSession, str]:
    lifecycle, units = charge_lifecycle(
        alpha_unit_ids=("charger",),
        game_id="order49-heroic",
        enemy_model_poses=compact_test_unit_poses(origin=Pose.at(10, 26), model_count=5),
        catalog=reroll_catalog() if natural else None,
    )
    state = lifecycle.state
    assert state is not None
    state.active_player_id = "player-b"
    state.replace_charge_phase_state(
        ChargePhaseState(
            battle_round=state.battle_round,
            active_player_id="player-b",
        ).with_phase_complete()
    )
    state.record_persisting_effect(
        PersistingEffect(
            effect_id="order49-enemy-charge",
            source_rule_id="order49-enemy-charge-source",
            owner_player_id="player-b",
            target_unit_instance_ids=(units["enemy"].unit_instance_id,),
            started_battle_round=state.battle_round,
            started_phase=BattlePhase.CHARGE,
            expiration=EffectExpiration.end_turn(
                battle_round=state.battle_round, player_id="player-b"
            ),
            effect_payload={"effect_kind": "charge_grants_fights_first"},
        )
    )
    state.gain_command_points(
        player_id="player-a",
        amount=3,
        source_id="order49-heroic-cp",
        source_kind=CommandPointSourceKind.OTHER,
    )
    from warhammer40k_core.engine.rules_units import rules_unit_view_by_id

    return LocalGameSession(lifecycle), rules_unit_view_by_id(
        state=state, unit_instance_id=units["charger"].unit_instance_id
    ).unit_instance_id


def ordinary_session(
    *, natural: bool, cp: int = 2, attached: bool = False
) -> tuple[LocalGameSession, str]:
    lifecycle, units = charge_lifecycle(
        alpha_unit_ids=("charger", "leader") if attached else ("charger",),
        alpha_attached_unit_ids=("charger", "leader") if attached else None,
        game_id="order49-ordinary",
        enemy_model_poses=compact_test_unit_poses(origin=Pose.at(10, 26), model_count=5),
        catalog=reroll_catalog() if natural else None,
    )
    state = lifecycle.state
    assert state is not None
    if cp:
        state.gain_command_points(
            player_id="player-a",
            amount=cp,
            source_id="order49-cp",
            source_kind=CommandPointSourceKind.OTHER,
        )
    from warhammer40k_core.engine.rules_units import rules_unit_view_by_id

    return LocalGameSession(lifecycle), rules_unit_view_by_id(
        state=state, unit_instance_id=units["charger"].unit_instance_id
    ).unit_instance_id
