"""Shooting's consumer of the shared target-replacement decision service."""

from __future__ import annotations

import hashlib
from dataclasses import dataclass, replace
from itertools import product
from typing import TYPE_CHECKING

from warhammer40k_core.core.ruleset import RulesetEdition
from warhammer40k_core.core.weapon_profiles import AbilityKind, AttackProfile
from warhammer40k_core.engine.decision_controller import DecisionController
from warhammer40k_core.engine.decision_record import DecisionRecord
from warhammer40k_core.engine.event_log import canonical_json, validate_json_value
from warhammer40k_core.engine.phase import GameLifecycleError, LifecycleStatus
from warhammer40k_core.engine.rules_units import rules_unit_view_by_id
from warhammer40k_core.engine.shooting_types import ShootingType
from warhammer40k_core.engine.target_replacement import (
    TargetReplacementContext,
    TargetReplacementOption,
    replacement_request,
)
from warhammer40k_core.engine.weapon_declaration import (
    RangedAttackPool,
    ShootingDeclarationProposal,
    ShootingProposalValidationResult,
    shooting_declaration_proposal_from_json,
)

if TYPE_CHECKING:
    from warhammer40k_core.engine.attack_sequence import AttackSequence
    from warhammer40k_core.engine.game_state import GameState
    from warhammer40k_core.engine.phases.shooting_handler import ShootingPhaseHandler


@dataclass(frozen=True, slots=True)
class ShootingTargetReplacement:
    context: TargetReplacementContext
    pool_indices: tuple[int, ...]
    pools_by_option_id: dict[str, dict[int, RangedAttackPool]]


def active_shooting_sequence(state: GameState) -> AttackSequence:
    out = state.out_of_phase_shooting_state
    if out is not None and out.attack_sequence is not None:
        return out.attack_sequence
    shooting = state.shooting_phase_state
    if shooting is None or shooting.attack_sequence is None:
        raise GameLifecycleError("Target replacement has no active Shooting action.")
    return shooting.attack_sequence


def replace_active_shooting_sequence(state: GameState, sequence: AttackSequence) -> None:
    current = active_shooting_sequence(state)
    if sequence.sequence_id != current.sequence_id:
        raise GameLifecycleError("Target replacement action identity drift.")
    out = state.out_of_phase_shooting_state
    if out is not None and out.attack_sequence is not None:
        state.replace_out_of_phase_shooting_state(
            out.with_attack_sequence_update(
                attack_sequence=sequence,
                allocated_model_ids=out.allocated_model_ids,
            )
        )
        return
    shooting = state.shooting_phase_state
    if shooting is None:
        raise GameLifecycleError("Target replacement Shooting state disappeared.")
    state.replace_shooting_phase_state(
        shooting.with_attack_sequence_update(
            attack_sequence=sequence,
            allocated_model_ids_this_phase=shooting.allocated_model_ids_this_phase,
        )
    )


def declaration_record_for_sequence(
    decisions: DecisionController,
    sequence: AttackSequence,
) -> tuple[DecisionRecord, ShootingDeclarationProposal]:
    for record in decisions.records:
        if sequence.sequence_id in (
            f"attack-sequence:{record.result.result_id}",
            f"out-of-phase-attack-sequence:{record.result.result_id}",
        ):
            proposal = shooting_declaration_proposal_from_json(record.result.payload)
            if (
                proposal.unit_instance_id != sequence.attacking_unit_instance_id
                or proposal.player_id != sequence.attacker_player_id
            ):
                raise GameLifecycleError("Replacement declaration authority drift.")
            return record, proposal
    raise GameLifecycleError("Replacement requires its recorded original declaration.")


def _base_attacks(
    decisions: DecisionController,
    record: DecisionRecord,
    original: ShootingDeclarationProposal,
    index: int,
    pool: RangedAttackPool,
) -> int:
    declaration = original.declarations[index]
    prefix = (
        f"{record.result.result_id}:declaration-{index + 1:03d}:"
        f"{declaration.attacker_model_instance_id}:{declaration.wargear_id}:"
        f"{declaration.weapon_profile_id}:{declaration.target_unit_instance_id}:attacks"
    )
    rolls = [
        event.payload
        for event in decisions.event_log.records
        if event.event_type == "random_characteristic_rolled"
        and isinstance(event.payload, dict)
        and event.payload.get("scope_id") == prefix
    ]
    if rolls:
        if len(rolls) != 1:
            raise GameLifecycleError("Committed random Attacks result is not unique.")
        value = rolls[0]["value"]
        if type(value) is not int or value <= 0:
            raise GameLifecycleError("Committed random Attacks result is invalid.")
        return value
    fixed = pool.weapon_profile.attack_profile.fixed_attacks
    if fixed is None:
        raise GameLifecycleError("Committed random Attacks result is missing.")
    return fixed


def _candidate_pool(
    *,
    handler: ShootingPhaseHandler,
    state: GameState,
    original: ShootingDeclarationProposal,
    index: int,
    target_id: str,
    base_attacks: int,
    attack_profile: AttackProfile,
    selected_ability_ids: tuple[str, ...] | None = None,
    validate_only: bool = False,
) -> RangedAttackPool | ShootingProposalValidationResult:
    from warhammer40k_core.engine.phases import shooting_declaration_validation as validation
    from warhammer40k_core.engine.phases.shooting_firing_deck import _available_weapons_for_model
    from warhammer40k_core.engine.phases.shooting_model import _AvailableWeapon
    from warhammer40k_core.engine.phases.shooting_validation import (
        _army_catalog_for_handler,
        _ruleset_descriptor_for_handler,
    )
    from warhammer40k_core.engine.ranged_weapon_keyword_effects import (
        weapon_profile_with_ranged_keyword_effects,
    )

    declaration = replace(original.declarations[index], target_unit_instance_id=target_id)
    if selected_ability_ids is not None:
        declaration = replace(declaration, selected_weapon_ability_ids=selected_ability_ids)
    rules_unit = rules_unit_view_by_id(state=state, unit_instance_id=original.unit_instance_id)
    source_model_id = declaration.firing_deck_source_model_instance_id
    if source_model_id is None:
        source = rules_unit.component_unit_for_model(declaration.attacker_model_instance_id)
        source_model_id = declaration.attacker_model_instance_id
    else:
        source_id = declaration.firing_deck_source_unit_instance_id
        if source_id is None:
            raise GameLifecycleError("Firing Deck replacement source is incomplete.")
        source = rules_unit_view_by_id(
            state=state, unit_instance_id=source_id
        ).component_unit_for_model(source_model_id)
    model = source.own_model_by_id(source_model_id)
    available = _available_weapons_for_model(
        model=model, army_catalog=_army_catalog_for_handler(handler)
    )
    matching = [
        w
        for w in available
        if w["weapon_instance_id"] == declaration.weapon_instance_id
        and w["weapon_profile"].profile_id == declaration.weapon_profile_id
        and w["wargear_id"] == declaration.wargear_id
    ]
    if len(matching) != 1:
        raise GameLifecycleError("Replacement cannot change a committed physical weapon.")
    profile = matching[0]["weapon_profile"]
    if not declaration.uses_firing_deck:
        profile = weapon_profile_with_ranged_keyword_effects(
            profile,
            state.persisting_effects_for_unit(source.unit_instance_id),
            owner_player_id=original.player_id,
        )
    committed: _AvailableWeapon = {
        "weapon_instance_id": declaration.weapon_instance_id,
        "model_instance_id": declaration.attacker_model_instance_id,
        "wargear_id": declaration.wargear_id,
        "weapon_profile": profile,
    }
    if declaration.firing_deck_source_unit_instance_id is not None:
        committed["firing_deck_source_unit_instance_id"] = (
            declaration.firing_deck_source_unit_instance_id
        )
        committed["firing_deck_source_model_instance_id"] = source_model_id
    result = validation._attack_pools_or_validation(
        state=state,
        proposal=replace(original, declarations=(declaration,)),
        ruleset_descriptor=_ruleset_descriptor_for_handler(handler),
        army_catalog=_army_catalog_for_handler(handler),
        shooting_player_id=original.player_id,
        out_of_phase_state=state.out_of_phase_shooting_state,
        shooting_target_restriction_hooks=handler.shooting_target_restriction_hooks,
        runtime_modifier_registry=handler.runtime_modifier_registry,
        committed_weapon=committed,
        committed_base_attacks=base_attacks,
        committed_attack_profile=attack_profile,
        validate_only=validate_only,
    )
    if isinstance(result, ShootingProposalValidationResult):
        return result
    return result[0][0]


def next_shooting_target_replacement(
    *,
    handler: ShootingPhaseHandler,
    state: GameState,
    decisions: DecisionController,
    sequence: AttackSequence,
) -> ShootingTargetReplacement | None:
    from warhammer40k_core.engine.phases.shooting_validation import _ruleset_descriptor_for_handler

    if _ruleset_descriptor_for_handler(handler).ruleset_id.edition is not RulesetEdition.ELEVENTH:
        return None
    if sequence.current_gathered_group is not None or sequence.is_complete:
        return None
    record, original = declaration_record_for_sequence(decisions, sequence)
    from warhammer40k_core.engine.shooting_target_replacement_authority import (
        validate_sequence_authority,
    )

    validate_sequence_authority(decisions, record, sequence)
    if len(original.declarations) != len(sequence.attack_pools):
        raise GameLifecycleError("Replacement weapon inventory drift.")
    from warhammer40k_core.engine.phases.shooting_validation import _enemy_placed_unit_ids

    for index, pool in enumerate(sequence.attack_pools):
        if index in sequence.used_pool_indices:
            continue
        base_attacks = _base_attacks(decisions, record, original, index, pool)
        existing = _candidate_pool(
            handler=handler,
            state=state,
            original=original,
            index=index,
            target_id=pool.target_unit_instance_id,
            base_attacks=base_attacks,
            attack_profile=pool.weapon_profile.attack_profile,
            selected_ability_ids=pool.selected_weapon_ability_ids,
            validate_only=True,
        )
        if isinstance(existing, RangedAttackPool) or existing.is_valid:
            continue
        indices = tuple(
            i
            for i, candidate in enumerate(sequence.attack_pools)
            if i not in sequence.used_pool_indices
            and (
                i == index
                or (
                    pool.shooting_type is ShootingType.SNAP
                    and candidate.shooting_type is ShootingType.SNAP
                )
            )
        )
        pools: dict[str, dict[int, RangedAttackPool]] = {}
        for target_id in _enemy_placed_unit_ids(state=state, player_id=sequence.attacker_player_id):
            if target_id == pool.target_unit_instance_id:
                continue
            alternatives: list[tuple[tuple[int, RangedAttackPool] | None, ...]] = []
            for candidate_index in indices:
                source_pool = sequence.attack_pools[candidate_index]
                choices = (
                    (),
                    *(
                        (ability.ability_id,)
                        for ability in source_pool.weapon_profile.abilities
                        if ability.ability_kind is AbilityKind.ANTI_KEYWORD
                    ),
                )
                candidates: list[tuple[int, RangedAttackPool] | None] = []
                for ability_ids in choices:
                    candidate = _candidate_pool(
                        handler=handler,
                        state=state,
                        original=original,
                        index=candidate_index,
                        target_id=target_id,
                        selected_ability_ids=ability_ids,
                        attack_profile=source_pool.weapon_profile.attack_profile,
                        base_attacks=_base_attacks(
                            decisions,
                            record,
                            original,
                            candidate_index,
                            source_pool,
                        ),
                    )
                    if isinstance(candidate, RangedAttackPool):
                        candidates.append((candidate_index, candidate))
                alternatives.append(tuple(candidates) if candidates else (None,))
            variants = [
                dict(item for item in variant if item is not None)
                for variant in product(*alternatives)
            ]
            variants = [variant for variant in variants if variant]
            for variant_index, target_pools in enumerate(variants):
                suffix = "" if len(variants) == 1 else f":abilities:{variant_index}"
                pools[f"target:{target_id}{suffix}"] = target_pools
        option_payloads = {
            key: {
                "pool_indices": list(indices),
                "replacement_pools": [
                    {"pool_index": i, "attack_pool": value.to_payload()}
                    for i, value in values.items()
                ],
                "forgone_pool_indices": [i for i in indices if i not in values],
            }
            for key, values in pools.items()
        }
        commitment = hashlib.sha256(
            canonical_json(
                {
                    "game_id": state.game_id,
                    "battle_round": state.battle_round,
                    "phase": state.current_battle_phase,
                    "active_player_id": state.active_player_id,
                    "physical_context": state.physical_proposal_context_hash(),
                    "sequence": sequence.to_payload(),
                    "invalid": existing.to_payload(),
                    "candidates": option_payloads,
                }
            ).encode()
        ).hexdigest()
        context = TargetReplacementContext(
            action_id=sequence.sequence_id,
            selection_id="weapons:" + ",".join(str(i) for i in indices),
            actor_id=sequence.attacker_player_id,
            source_unit_instance_id=sequence.attacking_unit_instance_id,
            original_target_ids=tuple(
                sorted({sequence.attack_pools[i].target_unit_instance_id for i in indices})
            ),
            invalid_target_ids=(pool.target_unit_instance_id,),
            source_context_hash=commitment,
            options=tuple(
                TargetReplacementOption(
                    key,
                    (next(iter(values.values())).target_unit_instance_id,),
                    validate_json_value(option_payloads[key]),
                    _replacement_label(state, values, len(indices)),
                )
                for key, values in pools.items()
            ),
        )
        return ShootingTargetReplacement(context, indices, pools)
    return None


def request_shooting_target_replacement(
    *,
    handler: ShootingPhaseHandler,
    state: GameState,
    decisions: DecisionController,
    sequence: AttackSequence,
) -> LifecycleStatus | None:
    replacement = next_shooting_target_replacement(
        handler=handler,
        state=state,
        decisions=decisions,
        sequence=sequence,
    )
    if replacement is None:
        return None
    request = replacement_request(
        request_id=state.next_decision_request_id(), context=replacement.context
    )
    decisions.request_decision(request)
    return LifecycleStatus.waiting_for_decision(stage=state.stage, decision_request=request)


def _replacement_label(state: GameState, pools: dict[int, RangedAttackPool], total: int) -> str:
    from warhammer40k_core.engine.phases.shooting_validation import _rules_unit_label

    target_id = next(iter(pools.values())).target_unit_instance_id
    label = _rules_unit_label(rules_unit_view_by_id(state=state, unit_instance_id=target_id))
    descriptions: list[str] = []
    for index, pool in pools.items():
        for ability in pool.weapon_profile.abilities:
            if ability.ability_id in pool.selected_weapon_ability_ids:
                descriptions.append(f"weapon {index + 1}: {ability.name}")
    forgone = total - len(pools)
    if forgone:
        descriptions.append(f"forgo {forgone} weapons")
    return label if not descriptions else f"{label} ({'; '.join(descriptions)})"
