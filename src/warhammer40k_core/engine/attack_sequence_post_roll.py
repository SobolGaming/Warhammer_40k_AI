from __future__ import annotations

from typing import TYPE_CHECKING, cast

from warhammer40k_core.core.weapon_profiles import WeaponKeyword, WeaponProfile
from warhammer40k_core.engine.attack_sequence_geometry_targets import _damage_value
from warhammer40k_core.engine.attack_sequence_hit_wound import (
    _devastating_wounds_resolution_for_attack,
    _emit_event,
    _melta_damage_modifier,
)
from warhammer40k_core.engine.attack_sequence_model import (
    SELECT_POST_ROLL_ATTACK_POOL_DECISION_TYPE,
    AttackResolutionContextPayload,
    AttackSequenceEvent,
    AttackSequenceHooks,
    AttackSequenceStep,
    HitRoll,
    HitRollPayload,
    WoundRollPayload,
)
from warhammer40k_core.engine.attack_sequence_state import AttackSequence
from warhammer40k_core.engine.decision_controller import DecisionController
from warhammer40k_core.engine.decision_request import DecisionOption, DecisionRequest
from warhammer40k_core.engine.decision_result import DecisionResult
from warhammer40k_core.engine.deferred_mortal_wounds import DeferredMortalWounds
from warhammer40k_core.engine.dice import DiceRollManager
from warhammer40k_core.engine.event_log import validate_json_value
from warhammer40k_core.engine.phase import GameLifecycleError, GameLifecycleStage, LifecycleStatus
from warhammer40k_core.engine.post_roll_attack_profiles import (
    POST_ROLL_ATTACK_PROFILE_POOLS_SOURCE_ID,
    PostRollAttackPoolSet,
    PostRollModifiedAttack,
)
from warhammer40k_core.engine.post_roll_weapon_profile_modifiers import (
    PostRollWeaponProfileModifierContext,
    ResolvedAttackRollValues,
    modified_post_roll_weapon_profile,
)
from warhammer40k_core.engine.rules_units import rules_unit_view_by_id
from warhammer40k_core.engine.runtime_modifiers import RuntimeModifierRegistry
from warhammer40k_core.engine.weapon_abilities import (
    DEVASTATING_WOUNDS_RULE_ID,
    DevastatingWoundsResolution,
    has_weapon_keyword,
)

if TYPE_CHECKING:
    from warhammer40k_core.engine.game_state import GameState
    from warhammer40k_core.engine.stratagems import StratagemCatalogIndex


def split_or_resume_post_roll_attack_pools(
    *,
    state: GameState,
    decisions: DecisionController,
    attack_sequence: AttackSequence,
    wounded_contexts: tuple[tuple[AttackSequence, AttackResolutionContextPayload], ...],
    runtime_modifier_registry: RuntimeModifierRegistry,
) -> tuple[
    AttackSequence,
    tuple[tuple[AttackSequence, AttackResolutionContextPayload], ...],
    LifecycleStatus | None,
]:
    current = attack_sequence
    if current.post_roll_attack_pools is None:
        active_player_id = state.active_player_id
        if active_player_id is None:
            raise GameLifecycleError("Post-roll attack pools require an active player.")
        modified_contexts = tuple(
            _post_roll_modified_wound_context(
                state=state,
                attack_sequence=wounded_sequence,
                attack_context=attack_context,
                runtime_modifier_registry=runtime_modifier_registry,
            )
            for wounded_sequence, attack_context in wounded_contexts
        )
        if all(
            modified_profile == wounded_sequence.current_pool().weapon_profile
            for (wounded_sequence, _attack_context), (modified_profile, _modified_context) in zip(
                wounded_contexts,
                modified_contexts,
                strict=True,
            )
        ):
            return current, wounded_contexts, None
        pool_set = PostRollAttackPoolSet.from_modified_attacks(
            sequence_id=current.sequence_id,
            active_player_id=active_player_id,
            attacks=tuple(
                PostRollModifiedAttack(
                    attack_context_id=modified_context["attack_context_id"],
                    weapon_profile=profile,
                )
                for profile, modified_context in modified_contexts
            ),
        )
        current = current.with_post_roll_attack_pools(
            pools=pool_set,
            attack_contexts=tuple(context for _profile, context in modified_contexts),
        )
        decisions.event_log.append(
            "post_roll_attack_pools_created",
            {
                "sequence_id": current.sequence_id,
                "active_player_id": pool_set.active_player_id,
                "source_rule_id": POST_ROLL_ATTACK_PROFILE_POOLS_SOURCE_ID,
                "post_roll_attack_pools": pool_set.to_payload(),
            },
        )
    pending_pool_set = current.post_roll_attack_pools
    if pending_pool_set is None:
        raise GameLifecycleError("Post-roll attack pool state was not retained.")
    pool_set = pending_pool_set
    if pool_set.selected_pool is None:
        if not pool_set.unresolved_pools:
            raise GameLifecycleError("Post-roll attack pool selection has no unresolved pools.")
        request = build_select_post_roll_attack_pool_request(
            request_id=state.next_decision_request_id(),
            state=state,
            attack_sequence=current,
        )
        if len(pool_set.unresolved_pools) > 1:
            decisions.request_decision(request)
            return (
                current,
                (),
                LifecycleStatus.waiting_for_decision(
                    stage=GameLifecycleStage.BATTLE,
                    decision_request=request,
                    payload={
                        "phase": current.source_phase.value,
                        "decision_type": SELECT_POST_ROLL_ATTACK_POOL_DECISION_TYPE,
                        "sequence_id": current.sequence_id,
                        "source_rule_id": POST_ROLL_ATTACK_PROFILE_POOLS_SOURCE_ID,
                    },
                ),
            )
        selected_pool = next(iter(pool_set.unresolved_pools))
        decisions.request_decision(request)
        auto_result = DecisionResult.for_request(
            result_id=f"{request.request_id}:auto-result",
            request=request,
            selected_option_id=selected_pool.pool_id,
        )
        decisions.submit_result(auto_result)
        current = apply_post_roll_attack_pool_decision(
            decisions=decisions,
            attack_sequence=current,
            result=auto_result,
        )
        selected_pool_set = current.post_roll_attack_pools
        if selected_pool_set is None:
            raise GameLifecycleError("Auto-selected post-roll attack pool was not retained.")
        pool_set = selected_pool_set
    selected = pool_set.selected_pool
    if selected is None:
        raise GameLifecycleError("Post-roll attack pool resolution requires a selected pool.")
    contexts_by_id = {
        context["attack_context_id"]: context for context in current.post_roll_attack_contexts
    }
    selected_contexts = tuple(
        (
            _attack_sequence_for_post_roll_context(
                attack_sequence=current,
                attack_context=contexts_by_id[context_id],
            ),
            contexts_by_id[context_id],
        )
        for context_id in selected.attack_context_ids
    )
    return current, selected_contexts, None


def build_select_post_roll_attack_pool_request(
    *,
    request_id: str,
    state: GameState,
    attack_sequence: AttackSequence,
) -> DecisionRequest:
    pool_set = attack_sequence.post_roll_attack_pools
    if pool_set is None or pool_set.selected_pool is not None:
        raise GameLifecycleError(
            "Post-roll attack pool selection requires unresolved unselected pools."
        )
    if pool_set.active_player_id != state.active_player_id:
        raise GameLifecycleError("Post-roll attack pool active player drift.")
    return DecisionRequest(
        request_id=request_id,
        decision_type=SELECT_POST_ROLL_ATTACK_POOL_DECISION_TYPE,
        actor_id=pool_set.active_player_id,
        payload={
            "submission_kind": SELECT_POST_ROLL_ATTACK_POOL_DECISION_TYPE,
            "game_id": state.game_id,
            "battle_round": state.battle_round,
            "phase": attack_sequence.source_phase.value,
            "sequence_id": attack_sequence.sequence_id,
            "active_player_id": pool_set.active_player_id,
            "attacker_player_id": attack_sequence.attacker_player_id,
            "source_rule_id": POST_ROLL_ATTACK_PROFILE_POOLS_SOURCE_ID,
            "pool_ids": [pool.pool_id for pool in pool_set.unresolved_pools],
        },
        options=tuple(
            DecisionOption(
                option_id=pool.pool_id,
                label=pool.pool_id,
                payload=validate_json_value(
                    {
                        "submission_kind": SELECT_POST_ROLL_ATTACK_POOL_DECISION_TYPE,
                        "sequence_id": attack_sequence.sequence_id,
                        "pool_id": pool.pool_id,
                        "weapon_profile": pool.weapon_profile.to_payload(),
                        "attack_context_ids": list(pool.attack_context_ids),
                        "source_rule_id": pool.source_rule_id,
                    }
                ),
            )
            for pool in pool_set.unresolved_pools
        ),
    )


def apply_post_roll_attack_pool_decision(
    *,
    decisions: DecisionController,
    attack_sequence: AttackSequence,
    result: DecisionResult,
) -> AttackSequence:
    record = decisions.record_for_result(result)
    result.validate_for_request(record.request)
    if result.decision_type != SELECT_POST_ROLL_ATTACK_POOL_DECISION_TYPE:
        raise GameLifecycleError("Post-roll attack pool decision type is invalid.")
    payload = result.payload
    if not isinstance(payload, dict):
        raise GameLifecycleError("Post-roll attack pool decision payload must be an object.")
    if payload.get("submission_kind") != SELECT_POST_ROLL_ATTACK_POOL_DECISION_TYPE:
        raise GameLifecycleError("Post-roll attack pool decision payload kind is invalid.")
    selected_pool_id = payload.get("pool_id")
    if type(selected_pool_id) is not str:
        raise GameLifecycleError("Post-roll attack pool decision requires pool_id.")
    if result.actor_id is None:
        raise GameLifecycleError("Post-roll attack pool decision requires an actor.")
    return attack_sequence.with_selected_post_roll_attack_pool(
        actor_id=result.actor_id,
        selected_pool_id=selected_pool_id,
    )


def _post_roll_modified_wound_context(
    *,
    state: GameState,
    attack_sequence: AttackSequence,
    attack_context: AttackResolutionContextPayload,
    runtime_modifier_registry: RuntimeModifierRegistry,
) -> tuple[WeaponProfile, AttackResolutionContextPayload]:
    pool = attack_sequence.current_pool()
    profile = modified_post_roll_weapon_profile(
        bindings=runtime_modifier_registry.post_roll_weapon_profile_modifier_bindings,
        context=PostRollWeaponProfileModifierContext(
            state=state,
            source_phase=attack_sequence.source_phase,
            attack_context_id=attack_context["attack_context_id"],
            attacking_unit_instance_id=attack_sequence.attacking_unit_instance_id,
            attacker_model_instance_id=pool.attacker_model_instance_id,
            target_unit_instance_id=attack_context["target_unit_instance_id"],
            hit_roll=_resolved_attack_roll_values(attack_context["hit_roll"]),
            wound_roll=_resolved_attack_roll_values(attack_context["wound_roll"]),
            weapon_profile=pool.weapon_profile,
        ),
    )
    return profile, cast(
        AttackResolutionContextPayload,
        {
            **attack_context,
            "weapon_profile_id": profile.profile_id,
            "damage_profile": profile.damage_profile.to_payload(),
        },
    )


def _resolved_attack_roll_values(
    payload: HitRollPayload | WoundRollPayload,
) -> ResolvedAttackRollValues:
    return ResolvedAttackRollValues(
        unmodified_roll=payload["unmodified_roll"],
        final_roll=payload["final_roll"],
        successful=payload["successful"],
        critical=payload["critical"],
        skipped=payload["skipped"],
    )


def _attack_sequence_for_post_roll_context(
    *,
    attack_sequence: AttackSequence,
    attack_context: AttackResolutionContextPayload,
) -> AttackSequence:
    return AttackSequence(
        sequence_id=attack_sequence.sequence_id,
        source_phase=attack_sequence.source_phase,
        attacker_player_id=attack_sequence.attacker_player_id,
        attacking_unit_instance_id=attack_sequence.attacking_unit_instance_id,
        attack_pools=attack_sequence.attack_pools,
        used_pool_indices=attack_sequence.used_pool_indices,
        selected_target_unit_instance_id=attack_sequence.selected_target_unit_instance_id,
        current_gathered_group=attack_sequence.current_gathered_group,
        pool_index=attack_context["pool_index"],
        attack_index=attack_context["attack_index"],
        generated_hit_index=attack_context["generated_hit_index"],
        current_hit_roll=(
            None
            if attack_context["generated_hit_index"] == 0
            else HitRoll.from_payload(attack_context["hit_roll"])
        ),
        deferred_mortal_wounds=attack_sequence.deferred_mortal_wounds,
        post_roll_attack_pools=attack_sequence.post_roll_attack_pools,
        post_roll_attack_contexts=attack_sequence.post_roll_attack_contexts,
    )


def defer_grouped_devastating_wounds(
    *,
    state: GameState,
    decisions: DecisionController,
    manager: DiceRollManager,
    attack_sequence: AttackSequence,
    wounded_contexts: tuple[tuple[AttackSequence, AttackResolutionContextPayload], ...],
    hooks: AttackSequenceHooks,
    stratagem_index: StratagemCatalogIndex | None,
    runtime_modifier_registry: RuntimeModifierRegistry,
    precision_priority_model_ids: tuple[str, ...],
) -> tuple[
    AttackSequence,
    tuple[tuple[AttackSequence, AttackResolutionContextPayload], ...],
    LifecycleStatus | None,
]:
    current = attack_sequence
    normal_contexts: list[tuple[AttackSequence, AttackResolutionContextPayload]] = []
    pool = attack_sequence.current_pool()
    for wounded_sequence, attack_context in wounded_contexts:
        target_keywords = rules_unit_view_by_id(
            state=state,
            unit_instance_id=attack_context["target_unit_instance_id"],
        ).keywords
        resolution = _devastating_wounds_resolution_for_attack(
            pool=pool,
            attack_context=attack_context,
            target_keywords=target_keywords,
        )
        if resolution is not DevastatingWoundsResolution.MORTAL_WOUNDS:
            normal_contexts.append((wounded_sequence, attack_context))
            continue
        damage_value, status = _damage_value(
            state=state,
            decisions=decisions,
            manager=manager,
            profile=pool.weapon_profile.damage_profile,
            attack_context_id=attack_context["attack_context_id"],
            attacker_player_id=attack_sequence.attacker_player_id,
            affected_unit_instance_id=attack_sequence.attacking_unit_instance_id,
            attacking_unit_instance_id=attack_sequence.attacking_unit_instance_id,
            attacker_model_instance_id=pool.attacker_model_instance_id,
            target_unit_instance_id=attack_context["target_unit_instance_id"],
            weapon_profile=pool.weapon_profile,
            source_phase=attack_sequence.source_phase,
            stratagem_index=stratagem_index,
            runtime_modifier_registry=runtime_modifier_registry,
        )
        if status is not None:
            return current, (), status
        if damage_value is None:
            raise GameLifecycleError("Damage roll did not resolve a value.")
        mortal_wounds = damage_value + _melta_damage_modifier(
            pool,
            target_keywords=target_keywords,
        )
        deferred = DeferredMortalWounds(
            source_rule_id=DEVASTATING_WOUNDS_RULE_ID,
            target_unit_instance_id=attack_context["target_unit_instance_id"],
            attack_context_id=attack_context["attack_context_id"],
            mortal_wounds=mortal_wounds,
            priority_model_ids=(
                precision_priority_model_ids
                if has_weapon_keyword(pool.weapon_profile, WeaponKeyword.PRECISION)
                else ()
            ),
        )
        _emit_event(
            decisions=decisions,
            hooks=hooks,
            event=AttackSequenceEvent(
                step=AttackSequenceStep.DAMAGE,
                sequence_id=wounded_sequence.sequence_id,
                attack_context_id=attack_context["attack_context_id"],
                pool_index=wounded_sequence.pool_index,
                attack_index=wounded_sequence.attack_index,
                payload=validate_json_value(
                    {
                        "saving_throw": None,
                        "damage_application": None,
                        "feel_no_pain": None,
                        "deferred_mortal_wounds": deferred.to_payload(),
                    }
                ),
            ),
        )
        decisions.event_log.append(
            "devastating_wounds_deferred",
            {
                "sequence_id": attack_sequence.sequence_id,
                "attack_context_id": attack_context["attack_context_id"],
                "target_unit_instance_id": attack_context["target_unit_instance_id"],
                "mortal_wounds": mortal_wounds,
                "source_rule_id": DEVASTATING_WOUNDS_RULE_ID,
            },
        )
        current = current.with_deferred_mortal_wounds(deferred)
    return current, tuple(normal_contexts), None
