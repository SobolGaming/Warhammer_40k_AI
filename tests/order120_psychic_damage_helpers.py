"""Conditional Core outcomes; the named example's activation is not implemented."""

from __future__ import annotations

import json
from pathlib import Path
from typing import cast

from tests.order116_mortal_helpers import additional_mortal_session
from warhammer40k_core.adapters.local_session import LocalGameSession
from warhammer40k_core.engine.additional_attack_mortal_permissions import (
    additional_attack_mortal_permission_effect,
)
from warhammer40k_core.engine.damage_allocation import FeelNoPainAttackCondition, FeelNoPainSource
from warhammer40k_core.engine.lifecycle import GameLifecycle
from warhammer40k_core.engine.phase import BattlePhase
from warhammer40k_core.rules.ability_damage_source import (
    AbilityDamageSource,
    ability_damage_source_at_data_boundary,
)
from warhammer40k_core.rules.objective_terminology import ObjectiveRuleScope
from warhammer40k_core.rules.source_data import RuleSourceText

SOURCE_ID = "gw-11e-2026-07-22-chaos-daemons:the-blue-scribes:xiratps-sorcerous-barrages"


def official_psychic_damage_source() -> AbilityDamageSource:
    audit = json.loads(
        (Path(__file__).parents[1] / "data/source_audits/order120/source.audit.json").read_text(
            encoding="utf-8"
        )
    )
    example = audit["official_example"]
    return ability_damage_source_at_data_boundary(
        RuleSourceText.from_raw(
            source_id=example["source_rule_id"],
            raw_text=example["operative_text"],
            objective_scope=ObjectiveRuleScope.NON_CORE_RULES,
        )
    )


def psychic_ability_damage_session(
    phase: BattlePhase, *, psychic: bool = True, weapon_psychic: bool = False
) -> LocalGameSession:
    session = additional_mortal_session(
        phase,
        mortal_wounds=12,
        attacks=3,
        armor_penetration=0,
        enemy_models=2,
        psychic=weapon_psychic,
    )
    state = session.lifecycle.state
    assert state is not None
    source, target = (army.units[0] for army in state.army_definitions)
    old = state.remove_persisting_effects_by_id(("order116:source-permission",))[0]
    assert isinstance(old.effect_payload, dict)
    descriptor = (
        official_psychic_damage_source()
        if psychic
        else ability_damage_source_at_data_boundary(
            RuleSourceText.from_raw(
                source_id=SOURCE_ID,
                raw_text="Ordinary ability: The target suffers mortal wounds.",
                objective_scope=ObjectiveRuleScope.NON_CORE_RULES,
            )
        )
    )
    state.record_persisting_effect(
        additional_attack_mortal_permission_effect(
            state=state,
            effect_id=old.effect_id,
            source_rule_id=descriptor.source_rule_id,
            source_model_instance_id=cast(str, old.effect_payload["source_model_instance_id"]),
            occasion_id=cast(str, old.effect_payload["occasion_id"]),
            mortal_wounds=12,
            weapon_scope="all",
            ability_damage_source=descriptor,
        )
    )
    for model in target.own_models:
        state.record_model_feel_no_pain_sources(
            model_instance_id=model.model_instance_id,
            sources=(
                FeelNoPainSource(
                    source_id="order120:psychic-only-fnp",
                    threshold=2,
                    attack_condition=FeelNoPainAttackCondition.PSYCHIC_ATTACK,
                ),
            ),
            decline_allowed=True,
        )
    assert source.unit_instance_id != target.unit_instance_id
    return LocalGameSession(lifecycle=GameLifecycle.from_payload(session.lifecycle.to_payload()))
