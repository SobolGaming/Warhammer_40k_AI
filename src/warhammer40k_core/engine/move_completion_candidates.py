from __future__ import annotations

from collections.abc import Callable

# Resolution and disposition remain owned by the existing typed move-effect service.
# pyright: reportPrivateUsage=false
from functools import partial

from warhammer40k_core.core.descriptor_hash import canonical_payload_sha256
from warhammer40k_core.engine import unit_move_completed_hooks as _hooks
from warhammer40k_core.engine.battle_shock_hooks import BattleShockHookRegistry
from warhammer40k_core.engine.event_log import JsonValue
from warhammer40k_core.engine.phase import GameLifecycleError, LifecycleStatus
from warhammer40k_core.engine.sequencing import SequencingParticipant, SequencingRequirement
from warhammer40k_core.engine.timing_rule_candidates import TimingRuleCandidate


def move_completion_candidates(
    *,
    context: _hooks.UnitMoveCompletedContext,
    mortal_wound_hooks: _hooks.UnitMoveCompletedMortalWoundHookRegistry,
    battle_shock_move_hooks: _hooks.UnitMoveCompletedBattleShockHookRegistry,
    battle_shock_hooks: BattleShockHookRegistry,
    additional_candidates: Callable[
        [_hooks.UnitMoveCompletedContext], tuple[TimingRuleCandidate, ...]
    ]
    | None = None,
) -> tuple[TimingRuleCandidate, ...]:
    decisions = context.decisions
    if decisions is None:
        raise GameLifecycleError("Move-completion sequencing requires decisions.")
    before = (context.state.to_payload(), decisions.to_payload())
    candidates: list[TimingRuleCandidate] = []
    for binding in mortal_wound_hooks.bindings:
        if binding.candidate_handler is not None:
            found = binding.candidate_handler(context)
            if type(found) is not tuple or any(
                type(item) is not TimingRuleCandidate for item in found
            ):
                raise GameLifecycleError("Move-completion providers require typed candidates.")
            candidates.extend(found)
        else:
            registry = _hooks.UnitMoveCompletedMortalWoundHookRegistry.from_bindings((binding,))
            for effect in registry.effects_for(context):
                candidates.append(
                    TimingRuleCandidate(
                        participant=SequencingParticipant(
                            participant_id=f"move-effect:{_hooks._effect_digest(effect)}",
                            player_id=effect.rolling_player_id,
                            source_rule_id=effect.source_rule_id,
                            requirement=SequencingRequirement.MANDATORY,
                            payload={"effect_key": _hooks._effect_key(effect)},
                        ),
                        activate=partial(resolve_mortal_wound_effects, context, (effect,)),
                    )
                )
    groups: dict[
        str, tuple[SequencingParticipant, list[_hooks.UnitMoveCompletedBattleShockEffect]]
    ] = {}
    for battle_shock_effect in battle_shock_move_hooks.effects_for(context):
        payload = battle_shock_effect.replay_payload
        owner = battle_shock_effect.source_player_id
        if owner not in context.state.player_ids:
            raise GameLifecycleError("Move-completed Battle-shock requires source rule ownership.")
        identity: dict[str, JsonValue] = {
            "source_rule_id": battle_shock_effect.source_rule_id,
            "hook_id": battle_shock_effect.hook_id,
            "source_player_id": owner,
            "trigger_event_id": context.trigger_event_id,
            "source_payload": {
                key: value
                for key, value in payload.items()
                if key not in {"target_unit_instance_id", "target_player_id"}
            }
            if isinstance(payload, dict)
            else payload,
        }
        identifier = f"move-battle-shock-rule:{canonical_payload_sha256(identity)}"
        participant = SequencingParticipant(
            participant_id=identifier,
            player_id=owner,
            source_rule_id=battle_shock_effect.source_rule_id,
            requirement=SequencingRequirement.MANDATORY,
            payload=identity,
        )
        if identifier not in groups:
            groups[identifier] = (participant, [])
        elif groups[identifier][0] != participant:
            raise GameLifecycleError("Move-completed Battle-shock rule identity drift.")
        groups[identifier][1].append(battle_shock_effect)
    for participant, effects in groups.values():
        candidates.append(
            TimingRuleCandidate(
                participant=participant,
                activate=partial(
                    resolve_battle_shock_effects, context, tuple(effects), battle_shock_hooks
                ),
            )
        )
    if additional_candidates is not None:
        candidates.extend(additional_candidates(context))
    if before != (context.state.to_payload(), decisions.to_payload()):
        raise GameLifecycleError("Move-completion discovery mutated authoritative state.")
    return tuple(candidates)


def resolve_mortal_wound_effects(
    context: _hooks.UnitMoveCompletedContext,
    effects: tuple[_hooks.UnitMoveCompletedMortalWoundEffect, ...],
) -> LifecycleStatus | None:
    decisions = context.decisions
    if decisions is None:
        raise GameLifecycleError("Move-completed mortal wounds require decisions.")
    for effect in effects:
        if _hooks._effect_key(effect) in _hooks.processed_effect_keys(decisions):
            continue
        status = _hooks.resolve_mortal_wound_effect(
            state=context.state,
            decisions=decisions,
            effect=effect,
            completed_phase=context.completed_phase,
            movement_action=context.movement_action,
        )
        if status is not None:
            return status
    return None


def resolve_battle_shock_effects(
    context: _hooks.UnitMoveCompletedContext,
    effects: tuple[_hooks.UnitMoveCompletedBattleShockEffect, ...],
    battle_shock_hooks: BattleShockHookRegistry,
) -> LifecycleStatus | None:
    decisions = context.decisions
    if decisions is None:
        raise GameLifecycleError("Move-completed Battle-shock requires decisions.")
    for effect in effects:
        if _hooks.unit_move_completed_battle_shock_effect_key(
            effect
        ) in _hooks.processed_battle_shock_effect_keys(decisions):
            continue
        status = _hooks.resolve_battle_shock_effect(
            state=context.state,
            decisions=decisions,
            effect=effect,
            battle_shock_hooks=battle_shock_hooks,
            runtime_modifier_registry=context.runtime_modifier_registry,
            ability_indexes_by_player_id=context.ability_indexes_by_player_id,
            completed_phase=context.completed_phase,
            movement_action=context.movement_action,
        )
        if status is not None:
            return status
    return None
