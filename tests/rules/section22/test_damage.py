"""Authenticated Psychic descriptor reaches native direct mortal/FNP consumer."""

import pytest

from tests.order120_psychic_damage_helpers import official_psychic_damage_source
from tests.support.section02_fixtures import Section02Definitions
from tests.support.section22_fixtures import pair
from warhammer40k_core.engine.ability_damage_context import ability_damage_source_context
from warhammer40k_core.engine.damage_allocation import (
    FeelNoPainAttackCondition,
    FeelNoPainSource,
    MortalWoundApplication,
)
from warhammer40k_core.engine.decision_controller import DecisionController
from warhammer40k_core.engine.destruction_provenance import DestructionSourceKind
from warhammer40k_core.engine.dice import DiceRollManager
from warhammer40k_core.engine.direct_mortal_wound_application import (
    apply_direct_mortal_wounds_to_unit,
)
from warhammer40k_core.engine.mortal_wound_destruction_evidence import (
    MortalWoundDestructionEvidence,
)
from warhammer40k_core.engine.phase import BattlePhase, GameLifecycleError
from warhammer40k_core.rules.ability_damage_source import ability_damage_source_at_data_boundary
from warhammer40k_core.rules.objective_terminology import ObjectiveRuleScope
from warhammer40k_core.rules.source_data import RuleSourceText


@pytest.mark.parametrize("psychic", [False, True])
@pytest.mark.parametrize("optional", [False, True])
def test_psychic_ability_wounds_reach_psychic_only_protection(
    section22_definitions: Section02Definitions, psychic: bool, optional: bool
) -> None:
    state, source, target = pair(section22_definitions, psychic=True)
    descriptor = (
        official_psychic_damage_source()
        if psychic
        else ability_damage_source_at_data_boundary(
            RuleSourceText.from_raw(
                source_id="constructed:s22:ordinary",
                raw_text="Ordinary ability: Target suffers mortal wounds.",
                objective_scope=ObjectiveRuleScope.NON_CORE_RULES,
            )
        )
    )
    state.record_model_feel_no_pain_sources(
        model_instance_id=target.own_model_ids()[0],
        sources=(
            FeelNoPainSource(
                source_id="constructed:s22:psychic-fnp",
                threshold=2,
                attack_condition=FeelNoPainAttackCondition.PSYCHIC_ATTACK,
            ),
        ),
        decline_allowed=optional,
    )
    decisions = DecisionController()
    evidence = MortalWoundDestructionEvidence.for_non_attack_state(
        state=state,
        destroying_player_id="owner",
        source_rules_unit_instance_id=source.unit_instance_id,
        source_model_instance_id=source.own_model_ids()[0],
        destruction_source_kind=DestructionSourceKind.ABILITY,
        action_phase=BattlePhase.COMMAND,
        source_step="constructed:s22:provider-authorized-outcome",
    )
    before = (state.to_payload(), decisions.to_payload())

    def apply() -> MortalWoundApplication:
        return apply_direct_mortal_wounds_to_unit(
            state=state,
            decisions=decisions,
            application_id="s22:direct",
            source_rule_id=descriptor.source_rule_id,
            source_context=ability_damage_source_context(
                source=descriptor, source_context={"source_rule_id": descriptor.source_rule_id}
            ),
            destruction_evidence=evidence,
            target_unit_instance_id=target.unit_instance_id,
            mortal_wounds=1,
            dice_manager=DiceRollManager(state.game_id, event_log=decisions.event_log),
            defender_player_id="opponent",
        )

    if psychic and optional:
        with pytest.raises(GameLifecycleError, match="choices require lifecycle routing"):
            apply()
        assert (state.to_payload(), decisions.to_payload()) == before
    else:
        result = apply()
        assert bool(result.feel_no_pain_resolutions) is psychic
        assert sum(a.wounds_lost for a in result.applications) + result.ignored_mortal_wounds == 1
