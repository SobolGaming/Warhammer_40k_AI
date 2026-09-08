from __future__ import annotations

from typing import TYPE_CHECKING

from warhammer40k_core.engine.model_destruction_cause_authority import ModelDestructionCauseKind
from warhammer40k_core.engine.mortal_wound_logical_death import MortalWoundLogicalDeathCauseBinding
from warhammer40k_core.engine.mortal_wound_target_lineage import (
    FROZEN_EMBARKED_RULES_UNIT_COMPONENTS_POLICY,
)
from warhammer40k_core.engine.phase import GameLifecycleError

if TYPE_CHECKING:
    from warhammer40k_core.engine.damage_allocation import MortalWoundApplicationProgress
    from warhammer40k_core.engine.game_state import GameState


def validate_initial_binding_source(
    *,
    state: GameState,
    progress: MortalWoundApplicationProgress,
    binding: MortalWoundLogicalDeathCauseBinding,
) -> None:
    if progress.destruction_evidence is not None:
        expected = MortalWoundLogicalDeathCauseBinding.fixed(
            cause_kind=ModelDestructionCauseKind.MORTAL_WOUND,
            producer_id=progress.application_id,
        )
        if binding != expected:
            raise GameLifecycleError("Mortal-wound application start binding drift.")
        return
    source_context = progress.source_context
    if not isinstance(source_context, dict):
        raise GameLifecycleError("Retained mortal-wound source context must be an object.")
    source_kind = source_context.get("source_kind")
    if source_kind == "hazardous":
        from warhammer40k_core.engine.hazardous_retention import (
            validate_retained_hazardous_progress,
        )

        validate_retained_hazardous_progress(state=state, progress=progress)
        return
    from warhammer40k_core.engine.attack_sequence_model import DEADLY_DEMISE_SOURCE_KIND
    from warhammer40k_core.engine.fight_unit_selected_grant_resolution import (
        SELECTED_TO_FIGHT_SELF_MORTAL_WOUNDS_SOURCE_KIND,
        validate_selected_to_fight_self_mortal_wound_progress,
    )
    from warhammer40k_core.engine.rule_deadly_demise_mortal_wound_routing import (
        RULE_MODEL_DESTRUCTION_DEADLY_DEMISE_SOURCE_KIND,
        rule_deadly_demise_logical_death_binding,
    )

    if source_kind == DEADLY_DEMISE_SOURCE_KIND:
        from warhammer40k_core.engine.lifecycle_state_queries import (
            active_attack_sequence_for_state,
        )
        from warhammer40k_core.engine.model_destruction_cause_attack_identity import (
            attack_damage_model_destruction_producer_id_for_context,
        )

        active_attack_sequence = active_attack_sequence_for_state(state)
        attack_context = source_context.get("attack_context")
        sequence_id = source_context.get("sequence_id")
        attack_context_id = (
            None
            if not isinstance(attack_context, dict)
            else attack_context.get("attack_context_id")
        )
        expected_binding = (
            None
            if not isinstance(sequence_id, str) or not isinstance(attack_context_id, str)
            else MortalWoundLogicalDeathCauseBinding.fixed(
                cause_kind=ModelDestructionCauseKind.ATTACK_DAMAGE,
                producer_id=attack_damage_model_destruction_producer_id_for_context(
                    sequence_id=sequence_id,
                    attack_context_id=attack_context_id,
                ),
            )
        )
        if (
            active_attack_sequence is None
            or sequence_id != active_attack_sequence.sequence_id
            or expected_binding is None
            or binding != expected_binding
        ):
            raise GameLifecycleError("Attack Deadly Demise application start binding drift.")
        return
    if source_kind == RULE_MODEL_DESTRUCTION_DEADLY_DEMISE_SOURCE_KIND:
        if binding != rule_deadly_demise_logical_death_binding():
            raise GameLifecycleError("Rule Deadly Demise application start binding drift.")
        return
    if source_kind == SELECTED_TO_FIGHT_SELF_MORTAL_WOUNDS_SOURCE_KIND:
        validate_selected_to_fight_self_mortal_wound_progress(progress)
        if binding != progress.logical_death_cause_binding:
            raise GameLifecycleError("Self mortal-wound application start binding drift.")
        return
    from warhammer40k_core.engine.transports import (
        TRANSPORT_HAZARD_MORTAL_WOUNDS_SOURCE_KIND,
    )

    if source_kind == TRANSPORT_HAZARD_MORTAL_WOUNDS_SOURCE_KIND:
        expected = MortalWoundLogicalDeathCauseBinding.fixed(
            cause_kind=ModelDestructionCauseKind.MORTAL_WOUND,
            producer_id=progress.application_id,
        )
        if (
            progress.target_lineage is None
            or progress.target_lineage.policy != FROZEN_EMBARKED_RULES_UNIT_COMPONENTS_POLICY
            or binding != expected
        ):
            raise GameLifecycleError("Embarked Transport hazard application start binding drift.")
        return
    raise GameLifecycleError("Retained mortal-wound application source is unsupported.")
