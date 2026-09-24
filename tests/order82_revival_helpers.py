"""Real revival producers with canonical attachments and retained presence."""

from __future__ import annotations

from copy import deepcopy

from tests.destruction_occurrence_fixture_helpers import destroy_rule_model_for_fixture
from tests.fight_on_death_helpers import retain_destroyed_model_for_fixture
from tests.phase15c_fight_order_helpers import fight_lifecycle
from warhammer40k_core.adapters.local_session import LocalGameSession
from warhammer40k_core.engine.battlefield_state import BattlefieldPlacementKind, UnitPlacement
from warhammer40k_core.engine.event_log import JsonValue, validate_json_value
from warhammer40k_core.engine.healing import (
    HealingEffect,
    healing_army_definitions_with_model_wounds,
    resolve_healing_until_blocked,
)
from warhammer40k_core.engine.healing_geometry import healing_phase_start_model_ids
from warhammer40k_core.engine.list_validation import AttachmentDeclaration
from warhammer40k_core.engine.phase import BattlePhase
from warhammer40k_core.engine.rules_units import rules_unit_view_by_id
from warhammer40k_core.geometry.pose import Pose


def revival_session(
    *,
    attached_target: bool = False,
    attached_enemy: bool = False,
    second_enemy: bool = False,
    retained_enemy: bool = False,
    destroyed_enemy: bool = False,
    revival_pose: Pose | None = None,
) -> tuple[LocalGameSession, dict[str, JsonValue]]:
    poses = {
        "recipient": tuple(Pose.at(10, 10 + 1.5 * i) for i in range(5)),
        "enemy": tuple(Pose.at(13 + 1.5 * i, 10) for i in range(5)),
    }
    alpha = ["recipient"]
    beta = ["enemy"]
    if attached_target:
        alpha.append("recipient-leader")
        poses["recipient-leader"] = (Pose.at(8.5, 14),)
    if attached_enemy:
        beta.append("enemy-leader")
        poses["enemy-leader"] = (Pose.at(14.5, 12),)
    if second_enemy:
        beta.append("new-enemy")
        poses["new-enemy"] = tuple(Pose.at(15 + 1.5 * i, 13) for i in range(5))
    leader_spec = ("core-character-leader", "core-character-leader", 1)
    lifecycle, units = fight_lifecycle(
        alpha_unit_ids=tuple(alpha),
        enemy_unit_ids=tuple(beta),
        origins={},
        poses_by_unit_key=poses,
        game_id="order82-revival",
        record_deployment=True,
        battle_phase=BattlePhase.FIGHT if retained_enemy else BattlePhase.COMMAND,
        alpha_unit_specs={"recipient-leader": leader_spec} if attached_target else None,
        enemy_unit_specs={"enemy-leader": leader_spec} if attached_enemy else None,
        alpha_attachment_declarations=(
            AttachmentDeclaration(
                source_unit_selection_id="recipient-leader", bodyguard_unit_selection_id="recipient"
            ),
        )
        if attached_target
        else (),
        enemy_attachment_declarations=(
            AttachmentDeclaration(
                source_unit_selection_id="enemy-leader", bodyguard_unit_selection_id="enemy"
            ),
        )
        if attached_enemy
        else (),
    )
    state = lifecycle.state
    assert state is not None
    assert state.battlefield_state is not None
    model_id = units["recipient"].own_models[-1].model_instance_id
    removed = state.battlefield_state.model_placement_by_id(model_id)
    destroy_rule_model_for_fixture(
        state=state,
        decisions=lifecycle.decision_controller,
        model_id=model_id,
        destroying_player_id="player-b",
        source_unit_id=units["enemy"].unit_instance_id,
        source_model_id=units["enemy"].own_models[0].model_instance_id,
    )
    if retained_enemy or destroyed_enemy:
        enemy_model_id = units["enemy"].own_models[0].model_instance_id
        if retained_enemy:
            placement = state.battlefield_state.model_placement_by_id(enemy_model_id)
            state.replace_army_definitions(
                list(
                    healing_army_definitions_with_model_wounds(
                        armies=tuple(state.army_definitions),
                        model_instance_id=enemy_model_id,
                        wounds_remaining=0,
                    )
                )
            )
            state.replace_battlefield_state(
                state.battlefield_state.with_removed_models((enemy_model_id,))
            )
            retain_destroyed_model_for_fixture(
                state=state,
                decisions=lifecycle.decision_controller,
                placement=placement,
                effect_id="order82-retained",
                source_rule_id="order82-retained-source",
                source_phase=BattlePhase.FIGHT,
            )
        else:
            destroy_rule_model_for_fixture(
                state=state,
                decisions=lifecycle.decision_controller,
                model_id=enemy_model_id,
                destroying_player_id="player-a",
                source_unit_id=units["recipient"].unit_instance_id,
                source_model_id=units["recipient"].own_models[0].model_instance_id,
            )
    target = rules_unit_view_by_id(
        state=state, unit_instance_id=units["recipient"].unit_instance_id
    )
    effect = HealingEffect(
        effect_id="order82-revival",
        target_unit_instance_id=target.unit_instance_id,
        amount=1,
        opposing_player_id="player-b",
        phase_start_model_ids=healing_phase_start_model_ids(state=state, rules_unit=target),
        source_context={"revive_model_full_health": True, "revive_destroyed_models_only": True},
    )
    _, request = resolve_healing_until_blocked(
        state=state,
        decisions=lifecycle.decision_controller,
        ruleset_descriptor=state.runtime_ruleset_descriptor(),
        effect=effect,
    )
    assert request is not None
    returned = removed.with_pose(Pose.at(12, 12) if revival_pose is None else revival_pose)
    session = LocalGameSession(lifecycle)
    session.advance_until_decision_or_terminal()
    # Retention setup decisions precede the replay root; revival submissions remain facade driven.
    session._initial_replay_lifecycle_payload = deepcopy(lifecycle.to_payload())  # pyright: ignore[reportPrivateUsage]
    return session, {
        "proposal_request_id": request.request_id,
        "proposal_kind": "healing_revival_placement",
        "unit_instance_id": returned.unit_instance_id,
        "placement_kind": BattlefieldPlacementKind.RETURN_TO_BATTLEFIELD.value,
        "attempted_placement": validate_json_value(
            UnitPlacement(
                army_id=returned.army_id,
                player_id=returned.player_id,
                unit_instance_id=returned.unit_instance_id,
                model_placements=(returned,),
            ).to_payload()
        ),
    }
