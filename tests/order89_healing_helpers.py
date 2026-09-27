"""Canonical mixed-model healing scenes with explicit casualty/phase history."""

from __future__ import annotations

from tests.destruction_occurrence_fixture_helpers import destroy_rule_model_for_fixture
from tests.healing_phase_start_helpers import record_healing_phase_start
from tests.phase15c_fight_order_helpers import fight_lifecycle
from warhammer40k_core.engine.battlefield_state import ModelPlacement
from warhammer40k_core.engine.healing import HealingEffect
from warhammer40k_core.engine.healing_geometry import healing_phase_start_model_ids
from warhammer40k_core.engine.lifecycle import GameLifecycle
from warhammer40k_core.engine.list_validation import AttachmentDeclaration
from warhammer40k_core.engine.phase import BattlePhase
from warhammer40k_core.engine.rules_units import rules_unit_view_by_id
from warhammer40k_core.geometry.pose import Pose


def healing_scene(
    *,
    wounded: tuple[int, ...] = (),
    destroyed: tuple[int, ...] = (),
    attached: bool = False,
    amount: int = 1,
    battle_phase: BattlePhase = BattlePhase.FIGHT,
) -> tuple[GameLifecycle, HealingEffect, tuple[str, ...], dict[str, ModelPlacement]]:
    lifecycle, units = fight_lifecycle(
        alpha_unit_ids=("recipient", "leader") if attached else ("recipient",),
        enemy_unit_ids=("enemy",),
        origins={},
        game_id="order89-healing",
        poses_by_unit_key={
            "recipient": tuple(Pose.at(10, 10 + 1.5 * i) for i in range(5)),
            "leader": (Pose.at(8.5, 10),),
            "enemy": tuple(Pose.at(40, 30 + 1.5 * i) for i in range(5)),
        },
        alpha_unit_specs={"leader": ("core-character-leader", "core-character-leader", 1)}
        if attached
        else None,
        alpha_attachment_declarations=(
            AttachmentDeclaration(
                source_unit_selection_id="leader", bodyguard_unit_selection_id="recipient"
            ),
        )
        if attached
        else (),
        record_deployment=True,
        battle_phase=battle_phase,
    )
    state = lifecycle.state
    assert state is not None
    assert state.battlefield_state is not None
    unit_id = units["recipient"].unit_instance_id
    target = rules_unit_view_by_id(state=state, unit_instance_id=unit_id)
    ids = tuple(
        m.model_instance_id
        for key in (("recipient", "leader") if attached else ("recipient",))
        for m in units[key].own_models
    )
    wound_models_with_recorded_priority(
        lifecycle, target.unit_instance_id, tuple(ids[i] for i in wounded)
    )
    placements = {ids[i]: state.battlefield_state.model_placement_by_id(ids[i]) for i in destroyed}
    for model_id in placements:
        destroy_rule_model_for_fixture(
            state=state,
            decisions=lifecycle.decision_controller,
            model_id=model_id,
            destroying_player_id="player-b",
            source_unit_id=None,
            source_model_id=None,
        )
    record_healing_phase_start(state=state, decisions=lifecycle.decision_controller)
    effect = HealingEffect(
        effect_id="order89-heal",
        target_unit_instance_id=target.unit_instance_id,
        amount=amount,
        opposing_player_id="player-b",
        phase_start_model_ids=healing_phase_start_model_ids(
            state=state,
            decisions=lifecycle.decision_controller,
            rules_unit=rules_unit_view_by_id(state=state, unit_instance_id=unit_id),
        ),
    )
    return lifecycle, effect, ids, placements


def wound_models_with_recorded_priority(
    lifecycle: GameLifecycle, unit_id: str, model_ids: tuple[str, ...]
) -> None:
    """A model-directed damage fixture, using real priority allocation and event authority."""
    from warhammer40k_core.engine.damage_allocation import (
        MortalWoundApplicationProgress,
        continue_mortal_wound_application,
    )
    from warhammer40k_core.engine.destruction_provenance import DestructionSourceKind
    from warhammer40k_core.engine.mortal_wound_destruction_evidence import (
        MortalWoundDestructionEvidence,
    )

    state = lifecycle.state
    assert state is not None
    assert state.current_battle_phase is not None
    for model_id in model_ids:
        routed = continue_mortal_wound_application(
            state=state,
            decisions=lifecycle.decision_controller,
            request_id=f"order89-wound:{model_id}",
            progress=MortalWoundApplicationProgress.start(
                application_id=f"order89-model-damage:{model_id}",
                source_rule_id="order89-model-directed-damage-fixture",
                source_context={"source_kind": "fixture", "model_instance_id": model_id},
                target_unit_instance_id=unit_id,
                defender_player_id="player-a",
                mortal_wounds=1,
                spill_over=False,
                priority_model_ids=(model_id,),
                destruction_evidence=MortalWoundDestructionEvidence.for_non_attack_state(
                    state=state,
                    destroying_player_id="player-b",
                    source_rules_unit_instance_id=None,
                    source_model_instance_id=None,
                    destruction_source_kind=DestructionSourceKind.ABILITY,
                    action_phase=state.current_battle_phase,
                    source_step="fixture",
                ),
            ),
        )
        assert routed.request is None
        assert routed.application is not None
        assert tuple(a.model_instance_id for a in routed.application.applications) == (model_id,)
