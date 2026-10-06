"""Conditional deployment-turn restrictions; this module grants no placement permission.

A deployment owner must first establish its granting rule and validate the oversized
deployment geometry. No admitted in-turn owner currently calls this seam. Constructed
conditional contexts exercise the restriction infrastructure without certifying one.
"""

from __future__ import annotations

from typing import TYPE_CHECKING, Literal

import msgspec

from warhammer40k_core.engine.effects import EffectExpiration, PersistingEffect
from warhammer40k_core.engine.event_log import validate_json_value
from warhammer40k_core.engine.phase import GameLifecycleError, GameLifecycleStage
from warhammer40k_core.engine.rules_unit_effects import rules_unit_effect_applications
from warhammer40k_core.engine.rules_units import rules_unit_view_by_id
from warhammer40k_core.rules.source_packages.warhammer_40000_11th import (
    core_large_model_setup_2026_09 as large_model_source,
)

if TYPE_CHECKING:
    from warhammer40k_core.engine.game_state import GameState

DEPLOYMENT_RESTRICTION_KIND = "large_model_deployment_turn_restriction"


class DeploymentRestrictionPayload(msgspec.Struct, frozen=True, forbid_unknown_fields=True):
    effect_kind: Literal["large_model_deployment_turn_restriction"]
    setup_occasion_id: str
    turn_player_id: str
    qualifying_model_instance_ids: tuple[str, ...]


def deployment_restriction_payload(effect: PersistingEffect) -> DeploymentRestrictionPayload | None:
    payload = effect.effect_payload
    if not isinstance(payload, dict) or payload.get("effect_kind") != DEPLOYMENT_RESTRICTION_KIND:
        if effect.effect_id.startswith("large-model-deployment:"):
            raise GameLifecycleError("Large-model deployment restriction payload is missing.")
        return None
    try:
        row = msgspec.convert(payload, type=DeploymentRestrictionPayload)
    except msgspec.ValidationError as exc:
        raise GameLifecycleError("Large-model deployment restriction payload is invalid.") from exc
    identifiers = (row.setup_occasion_id, row.turn_player_id, *row.qualifying_model_instance_ids)
    if (
        any(not value or value != value.strip() for value in identifiers)
        or not row.qualifying_model_instance_ids
        or row.qualifying_model_instance_ids
        != tuple(sorted(set(row.qualifying_model_instance_ids)))
        or len(effect.target_unit_instance_ids) != 1
        or effect.source_rule_id != large_model_source.SETUP_POLICY.source_rule_id
        or effect.effect_id != f"large-model-deployment:{row.setup_occasion_id}"
        or effect.started_phase is None
        or effect.expiration
        != EffectExpiration.end_turn(
            battle_round=effect.started_battle_round, player_id=row.turn_player_id
        )
    ):
        raise GameLifecycleError("Large-model deployment restriction source or turn drifted.")
    return row


def record_conditional_deployment_restriction(
    *,
    state: GameState,
    unit_instance_id: str,
    qualifying_model_instance_ids: tuple[str, ...],
    setup_occasion_id: str,
) -> PersistingEffect | None:
    """Record an already-qualified condition, never deploy or qualify a model.

    Qualifying IDs attest the caller's oversized geometry result, not a new grant.
    Pregame setup occurs outside turns and creates no first-turn restriction.
    The active turn may belong to the opponent of the affected unit's owner.
    """
    if state.stage is GameLifecycleStage.SETUP:
        return None
    if (
        state.stage is not GameLifecycleStage.BATTLE
        or state.active_player_id is None
        or state.current_battle_phase is None
    ):
        raise GameLifecycleError("Conditional deployment restriction requires a battle turn.")
    view = rules_unit_view_by_id(state=state, unit_instance_id=unit_instance_id)
    model_ids = {model.model_instance_id for model in view.own_models}
    if not qualifying_model_instance_ids or not set(qualifying_model_instance_ids).issubset(
        model_ids
    ):
        raise GameLifecycleError("Conditional deployment restriction model identity drifted.")
    effect = PersistingEffect(
        effect_id=f"large-model-deployment:{setup_occasion_id}",
        source_rule_id=large_model_source.SETUP_POLICY.source_rule_id,
        owner_player_id=view.owner_player_id,
        target_unit_instance_ids=(view.unit_instance_id,),
        started_battle_round=state.battle_round,
        started_phase=state.current_battle_phase,
        expiration=EffectExpiration.end_turn(
            battle_round=state.battle_round, player_id=state.active_player_id
        ),
        effect_payload=validate_json_value(
            msgspec.to_builtins(
                DeploymentRestrictionPayload(
                    effect_kind="large_model_deployment_turn_restriction",
                    setup_occasion_id=setup_occasion_id,
                    turn_player_id=state.active_player_id,
                    qualifying_model_instance_ids=qualifying_model_instance_ids,
                )
            )
        ),
    )
    deployment_restriction_payload(effect)
    state.record_persisting_effect(effect)
    return effect


def conditional_deployment_prevents_activity(*, state: GameState, unit_instance_id: str) -> bool:
    if not any(
        effect.effect_id.startswith("large-model-deployment:")
        for effect in state.persisting_effects
    ):
        return False
    for application in rules_unit_effect_applications(state, unit_instance_id):
        effect = application.effect
        row = deployment_restriction_payload(effect)
        if row is not None and (
            effect.started_battle_round == state.battle_round
            and row.turn_player_id == state.active_player_id
        ):
            return True
    return False
