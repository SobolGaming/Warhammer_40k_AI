"""Melee consumer of source-backed 04.03.03, preserving declared attack splits."""

from __future__ import annotations

import hashlib
from dataclasses import dataclass, replace
from typing import TYPE_CHECKING

from warhammer40k_core.core.army_catalog import ArmyCatalog
from warhammer40k_core.core.ruleset_descriptor import RulesetDescriptor
from warhammer40k_core.engine.attack_sequence import AttackSequence
from warhammer40k_core.engine.attack_weapon_inventory import melee_weapon_selection_context
from warhammer40k_core.engine.battlefield_presence import battlefield_scenario_for_state
from warhammer40k_core.engine.decision_controller import DecisionController
from warhammer40k_core.engine.decision_request import DecisionRequest
from warhammer40k_core.engine.event_log import canonical_json, validate_json_value
from warhammer40k_core.engine.fight_resolution import (
    _melee_target_unit_ids_for_model,
    melee_declaration_proposal_from_payload,
    target_model_ids_for_melee_attack,
)
from warhammer40k_core.engine.game_state import GameState
from warhammer40k_core.engine.melee_weapon_commitment import (
    commitment_for_activation,
    object_payload,
)
from warhammer40k_core.engine.phase import GameLifecycleError, LifecycleStatus
from warhammer40k_core.engine.rules_units import rules_unit_view_by_id
from warhammer40k_core.engine.runtime_modifiers import RuntimeModifierRegistry
from warhammer40k_core.engine.target_replacement import (
    TargetReplacementContext,
    TargetReplacementOption,
    replacement_request,
)
from warhammer40k_core.engine.weapon_declaration import RangedAttackPool
from warhammer40k_core.engine.weapon_instances import equipped_weapon_profile_instances_for_model

if TYPE_CHECKING:
    from warhammer40k_core.engine.lifecycle import GameLifecycle


@dataclass(frozen=True, slots=True)
class MeleeTargetReplacement:
    context: TargetReplacementContext
    pool_indices: tuple[int, ...]
    pools_by_option_id: dict[str, dict[int, RangedAttackPool]]


def active_melee_sequence(state: GameState) -> AttackSequence:
    fight = state.fight_phase_state
    if fight is None or fight.attack_sequence is None:
        raise GameLifecycleError("Target replacement requires an active melee sequence.")
    return fight.attack_sequence


def is_melee_replacement(state: GameState, request: DecisionRequest) -> bool:
    fight = state.fight_phase_state
    if fight is None or fight.attack_sequence is None:
        return False
    body = object_payload(request.payload)
    return body.get("action_id") == fight.attack_sequence.sequence_id


def replace_active_melee_sequence(state: GameState, sequence: AttackSequence) -> None:
    fight = state.fight_phase_state
    if fight is None or active_melee_sequence(state).sequence_id != sequence.sequence_id:
        raise GameLifecycleError("Melee replacement action identity drifted.")
    state.replace_fight_phase_state(
        fight.with_attack_sequence_update(
            attack_sequence=sequence,
            allocated_model_ids_this_phase=fight.allocated_model_ids_this_phase,
        )
    )


def next_melee_target_replacement(
    *,
    state: GameState,
    decisions: DecisionController,
    sequence: AttackSequence,
    ruleset_descriptor: RulesetDescriptor,
    army_catalog: ArmyCatalog,
    runtime_modifier_registry: RuntimeModifierRegistry,
) -> MeleeTargetReplacement | None:
    if sequence.current_gathered_group is not None or sequence.is_complete:
        return None
    events = [
        object_payload(event.payload)
        for event in decisions.event_log.records
        if event.event_type == "melee_declaration_accepted"
        and object_payload(event.payload).get("attack_sequence_id") == sequence.sequence_id
    ]
    if len(events) != 1:
        raise GameLifecycleError("Melee replacement requires its original declaration.")
    proposal = melee_declaration_proposal_from_payload(events[0]["proposal"])
    if commitment_for_activation(decisions, proposal.source_decision_result_id) is None:
        return None
    scenario = battlefield_scenario_for_state(state=state)
    source = rules_unit_view_by_id(state=state, unit_instance_id=proposal.unit_instance_id)
    for index, pool in enumerate(sequence.attack_pools):
        if index in sequence.used_pool_indices:
            continue
        unit = source.component_unit_for_model(pool.attacker_model_instance_id)
        physical_targets = _melee_target_unit_ids_for_model(
            scenario=scenario,
            ruleset_descriptor=ruleset_descriptor,
            unit_instance_id=unit.unit_instance_id,
            model_instance_id=pool.attacker_model_instance_id,
            state=state,
            source_decision_result_id=proposal.source_decision_result_id,
        )
        targets: dict[str, list[str]] = {}
        for target in physical_targets:
            canonical = rules_unit_view_by_id(state=state, unit_instance_id=target).unit_instance_id
            targets.setdefault(canonical, []).append(target)
        if pool.target_unit_instance_id in targets:
            continue
        weapons = [
            weapon
            for weapon in equipped_weapon_profile_instances_for_model(
                model=unit.own_model_by_id(pool.attacker_model_instance_id),
                army_catalog=army_catalog,
            )
            if weapon.weapon_instance_id == pool.weapon_instance_id
            and weapon.weapon_profile.profile_id == pool.weapon_profile_id
        ]
        if len(weapons) != 1:
            raise GameLifecycleError("Melee replacement physical weapon identity drifted.")
        alternatives: dict[str, dict[int, RangedAttackPool]] = {}
        for target, aliases in sorted(targets.items()):
            models = tuple(
                sorted(
                    {
                        model
                        for alias in aliases
                        for model in target_model_ids_for_melee_attack(
                            scenario=scenario,
                            ruleset_descriptor=ruleset_descriptor,
                            unit_instance_id=unit.unit_instance_id,
                            model_instance_id=pool.attacker_model_instance_id,
                            target_unit_instance_id=alias,
                            state=state,
                            source_decision_result_id=proposal.source_decision_result_id,
                        )
                    }
                )
            )
            current_context = melee_weapon_selection_context(
                state=state,
                runtime_modifier_registry=runtime_modifier_registry,
                attacking_unit_instance_id=unit.unit_instance_id,
                attacker_model_instance_id=pool.attacker_model_instance_id,
                weapon_instance_id=pool.weapon_instance_id,
                source_request_id=proposal.source_decision_result_id,
                target_unit_instance_ids=(target,),
                profile=weapons[0].weapon_profile,
            )
            context = (
                current_context
                if pool.weapon_selection_context is None
                else (
                    pool.weapon_selection_context.with_resolved_profile(
                        target,
                        current_context.raw_profile_for_target(target),
                    )
                )
            )
            profile = context.selected_profile(target, pool.selected_weapon_ability_ids)
            # Counts and selected weapon abilities belong to the accepted declaration.
            # Replacement changes only the destination of this unresolved allocation.
            alternatives[f"target:{target}"] = {
                index: replace(
                    pool,
                    weapon_profile=profile,
                    weapon_selection_context=context if pool.selected_weapon_ability_ids else None,
                    target_unit_instance_id=target,
                    target_visible_model_ids=models,
                    target_in_range_model_ids=models,
                )
            }
        options = tuple(
            TargetReplacementOption(
                option_id=option_id,
                target_ids=(replacement[index].target_unit_instance_id,),
                selection_payload=validate_json_value(
                    {
                        "pool_indices": [index],
                        "replacement_pools": [
                            {"pool_index": index, "attack_pool": replacement[index].to_payload()}
                        ],
                        "forgone_pool_indices": [],
                    }
                ),
            )
            for option_id, replacement in alternatives.items()
        )
        replacement_context = TargetReplacementContext(
            action_id=sequence.sequence_id,
            selection_id=f"weapons:{index}",
            actor_id=sequence.attacker_player_id,
            source_unit_instance_id=sequence.attacking_unit_instance_id,
            original_target_ids=(pool.target_unit_instance_id,),
            invalid_target_ids=(pool.target_unit_instance_id,),
            source_context_hash=hashlib.sha256(
                canonical_json(
                    {
                        "physical_context": state.physical_proposal_context_hash(),
                        "sequence": sequence.to_payload(),
                        "pool_index": index,
                        "options": [option.selection_payload for option in options],
                    }
                ).encode()
            ).hexdigest(),
            options=options,
        )
        return MeleeTargetReplacement(replacement_context, (index,), alternatives)
    return None


def request_melee_target_replacement(
    *,
    state: GameState,
    decisions: DecisionController,
    sequence: AttackSequence,
    ruleset_descriptor: RulesetDescriptor,
    army_catalog: ArmyCatalog,
    runtime_modifier_registry: RuntimeModifierRegistry,
) -> LifecycleStatus | None:
    current = next_melee_target_replacement(
        state=state,
        decisions=decisions,
        sequence=sequence,
        ruleset_descriptor=ruleset_descriptor,
        army_catalog=army_catalog,
        runtime_modifier_registry=runtime_modifier_registry,
    )
    if current is None:
        return None
    request = replacement_request(
        request_id=state.next_decision_request_id(), context=current.context
    )
    decisions.request_decision(request)
    return LifecycleStatus.waiting_for_decision(stage=state.stage, decision_request=request)


def current_melee_replacement(host: GameLifecycle) -> MeleeTargetReplacement | None:
    if host.state is None:
        raise GameLifecycleError("Melee replacement requires a configured game.")
    return next_melee_target_replacement(
        state=host.state,
        decisions=host.decision_controller,
        sequence=active_melee_sequence(host.state),
        ruleset_descriptor=host.config.ruleset_descriptor,
        army_catalog=host.config.army_catalog,
        runtime_modifier_registry=host._fight_phase_handler.runtime_modifier_registry,  # pyright: ignore[reportPrivateUsage]
    )
