"""19.04 keeps attached-unit ability sources through their destroying attacks.

This semantic lifetime grants no physical presence or right to act. Special
Fight/Shoot-on-death retention remains owned by retained_destruction_state.
"""

from __future__ import annotations

from typing import TYPE_CHECKING

from warhammer40k_core.core.validation import IdentifierValidator
from warhammer40k_core.engine.destruction_provenance import DestructionSourceKind
from warhammer40k_core.engine.effects import EffectExpiration, PersistingEffect
from warhammer40k_core.engine.event_log import JsonValue
from warhammer40k_core.engine.phase import GameLifecycleError
from warhammer40k_core.engine.rules_units import rules_unit_view_by_id

if TYPE_CHECKING:
    from warhammer40k_core.engine.decision_controller import DecisionController
    from warhammer40k_core.engine.game_state import GameState
    from warhammer40k_core.engine.mortal_wound_destruction_evidence import (
        MortalWoundDestructionEvidence,
    )

ATTACK_ABILITY_SOURCE_RULE_ID = "rule:19:19.04:1"
ATTACK_ABILITY_SOURCE_KIND = "attack_scoped_attached_ability_source"
ATTACK_ABILITY_SOURCE_RETAINED_EVENT = "attack_ability_source_retained"
ATTACK_ABILITY_SOURCE_EXPIRED_EVENT = "attack_ability_sources_expired"
_identifier = IdentifierValidator(GameLifecycleError)


def retain_attack_mortal_ability_source(
    *,
    state: GameState,
    decisions: DecisionController,
    evidence: MortalWoundDestructionEvidence | None,
    source_context: JsonValue,
    model_instance_id: str,
) -> None:
    if evidence is None or evidence.destruction_source_kind is not DestructionSourceKind.ATTACK:
        return
    view = rules_unit_view_by_id(
        state=state, unit_instance_id=state.unit_instance_id_for_model(model_instance_id)
    )
    if not view.is_attached_rules_unit:
        return
    if not isinstance(source_context, dict):
        raise GameLifecycleError("Attack mortal ability source requires sequence context.")
    sequence_id = _identifier("Attack mortal sequence_id", source_context.get("sequence_id"))
    retain_attack_ability_source(
        state=state,
        decisions=decisions,
        sequence_id=sequence_id,
        model_instance_id=model_instance_id,
    )


def retain_attack_ability_source(
    *,
    state: GameState,
    decisions: DecisionController,
    sequence_id: str,
    model_instance_id: str,
) -> None:
    sequence_id = _identifier("Attack ability source sequence_id", sequence_id)
    model_instance_id = _identifier("Attack ability source model_instance_id", model_instance_id)
    unit_id = state.unit_instance_id_for_model(model_instance_id)
    view = rules_unit_view_by_id(state=state, unit_instance_id=unit_id)
    if not view.is_attached_rules_unit:
        return
    model = next(model for model in view.own_models if model.model_instance_id == model_instance_id)
    if model.is_alive:
        raise GameLifecycleError("Attack ability source retention requires a destroyed model.")
    phase = state.current_battle_phase
    player_id = state.active_player_id
    if phase is None or player_id is None:
        raise GameLifecycleError("Attack ability source retention requires an active phase.")
    effect = PersistingEffect(
        effect_id=f"attack-ability-source:{sequence_id}:{model_instance_id}",
        source_rule_id=ATTACK_ABILITY_SOURCE_RULE_ID,
        owner_player_id=view.owner_player_id,
        target_unit_instance_ids=(view.unit_instance_id,),
        started_battle_round=state.battle_round,
        started_phase=phase,
        # The attack executor removes it first; phase end is only the outer limit.
        expiration=EffectExpiration.end_phase(
            battle_round=state.battle_round, phase=phase, player_id=player_id
        ),
        effect_payload={
            "effect_kind": ATTACK_ABILITY_SOURCE_KIND,
            "sequence_id": sequence_id,
            "model_instance_id": model_instance_id,
            "physical_unit_instance_id": unit_id,
        },
    )
    prior = [stored for stored in state.persisting_effects if stored.effect_id == effect.effect_id]
    if prior:
        if prior != [effect]:
            raise GameLifecycleError("Attack ability source retention drift.")
        return
    state.record_persisting_effect(effect)
    decisions.event_log.append(ATTACK_ABILITY_SOURCE_RETAINED_EVENT, effect.to_payload())


def expire_attack_ability_sources(
    *, state: GameState, decisions: DecisionController, sequence_id: str
) -> None:
    sequence_id = _identifier("Attack ability source sequence_id", sequence_id)
    expired = [
        effect
        for effect in state.persisting_effects
        if (payload := _source_payload(effect)) is not None
        and payload["sequence_id"] == sequence_id
    ]
    if not expired:
        return
    expired_ids = {effect.effect_id for effect in expired}
    state.remove_persisting_effects_by_id(tuple(sorted(expired_ids)))
    decisions.event_log.append(
        ATTACK_ABILITY_SOURCE_EXPIRED_EVENT,
        {
            "sequence_id": sequence_id,
            "source_rule_id": ATTACK_ABILITY_SOURCE_RULE_ID,
            "effect_ids": sorted(expired_ids),
        },
    )


def attack_ability_source_model_ids(
    *, state: GameState, rules_unit_instance_id: str
) -> tuple[str, ...]:
    view = rules_unit_view_by_id(state=state, unit_instance_id=rules_unit_instance_id)
    candidates = [
        effect
        for effect in state.persisting_effects
        if isinstance(effect.effect_payload, dict)
        and effect.effect_payload.get("effect_kind") == ATTACK_ABILITY_SOURCE_KIND
    ]
    if not candidates:
        return ()
    from warhammer40k_core.engine.aura_applications import persisting_effects_for_lineage
    from warhammer40k_core.engine.unit_split_views import split_effect_predecessor_ids

    model_ids: set[str] = set()
    for effect in persisting_effects_for_lineage(
        candidates,
        split_effect_predecessor_ids(
            armies=tuple(state.army_definitions), unit_instance_id=view.unit_instance_id
        ),
    ):
        payload = _source_payload(effect)
        if payload is None:
            continue
        model_id = _identifier(
            "Attack ability source model_instance_id", payload["model_instance_id"]
        )
        if (
            effect.target_unit_instance_ids != (view.unit_instance_id,)
            or state.unit_instance_id_for_model(model_id) != payload["physical_unit_instance_id"]
            or not view.is_attached_rules_unit
            or model_id not in {model.model_instance_id for model in view.own_models}
            or effect.started_battle_round != state.battle_round
            or effect.started_phase is not state.current_battle_phase
            or effect.expiration.player_id != state.active_player_id
        ):
            raise GameLifecycleError("Attack ability source lineage or lifetime drift.")
        # A legal revival restores ordinary presence, without duplicate authority.
        if any(
            model.model_instance_id == model_id and not model.is_alive for model in view.own_models
        ):
            model_ids.add(model_id)
    return tuple(sorted(model_ids))


def _source_payload(effect: PersistingEffect) -> dict[str, JsonValue] | None:
    payload = effect.effect_payload
    if not isinstance(payload, dict) or payload.get("effect_kind") != ATTACK_ABILITY_SOURCE_KIND:
        return None
    if effect.source_rule_id != ATTACK_ABILITY_SOURCE_RULE_ID or set(payload) != {
        "effect_kind",
        "sequence_id",
        "model_instance_id",
        "physical_unit_instance_id",
    }:
        raise GameLifecycleError("Attack ability source fields drift.")
    for key in ("sequence_id", "model_instance_id", "physical_unit_instance_id"):
        _identifier("Attack ability source " + key, payload[key])
    return payload
