from __future__ import annotations

import json
from dataclasses import replace
from typing import Any, cast

from warhammer40k_core.core.dice import DiceRollResult, DiceRollSpec
from warhammer40k_core.core.ruleset_descriptor import RulesetDescriptor
from warhammer40k_core.core.weapon_profiles import (
    DamageProfile,
    RangeProfile,
    WeaponKeyword,
    WeaponProfile,
)
from warhammer40k_core.engine.attack_sequence import (
    AttackSequence,
    apply_damage_allocation_model_decision,
    attack_sequence_hit_roll_spec,
    attack_sequence_wound_roll_spec,
)
from warhammer40k_core.engine.damage_allocation import (
    SELECT_DAMAGE_ALLOCATION_MODEL_DECISION_TYPE,
)
from warhammer40k_core.engine.decision_controller import DecisionController
from warhammer40k_core.engine.decision_result import DecisionResult
from warhammer40k_core.engine.destruction_provenance import (
    DestructionAttackKind,
    DestructionProvenance,
)
from warhammer40k_core.engine.dice import DiceRollManager
from warhammer40k_core.engine.game_state import GameState
from warhammer40k_core.engine.lifecycle import GameLifecycle, GameLifecyclePayload
from warhammer40k_core.engine.phase import LifecycleStatus
from warhammer40k_core.engine.saves import SaveKind, saving_throw_roll_spec


def battle_lifecycle_payload(
    *,
    state: GameState,
    decisions: DecisionController,
) -> GameLifecyclePayload:
    lifecycle = GameLifecycle(state=state, decision_controller=decisions)
    return cast(
        GameLifecyclePayload,
        json.loads(json.dumps(lifecycle.to_payload(), sort_keys=True)),
    )


def apply_pending_damage_allocation(
    *,
    state: GameState,
    decisions: DecisionController,
    ruleset_descriptor: RulesetDescriptor,
    attack_sequence: AttackSequence | None,
    status: LifecycleStatus | None,
    already_allocated_model_ids: tuple[str, ...],
    dice_manager: DiceRollManager,
    selected_model_id: str,
) -> tuple[AttackSequence | None, tuple[str, ...], LifecycleStatus | None]:
    if attack_sequence is None or status is None or status.decision_request is None:
        raise AssertionError("Expected a pending grouped-damage allocation decision.")
    request = status.decision_request
    if request.decision_type != SELECT_DAMAGE_ALLOCATION_MODEL_DECISION_TYPE:
        raise AssertionError("Expected a damage-allocation model decision.")
    result = DecisionResult.for_request(
        result_id=f"result:test-damage-allocation:{selected_model_id}",
        request=request,
        selected_option_id=selected_model_id,
    )
    decisions.submit_result(result)
    return apply_damage_allocation_model_decision(
        state=state,
        decisions=decisions,
        ruleset_descriptor=ruleset_descriptor,
        attack_sequence=attack_sequence,
        result=result,
        already_allocated_model_ids=already_allocated_model_ids,
        dice_manager=dice_manager,
    )


def successful_attack_roll_results(
    *,
    attack_sequence: AttackSequence,
    attacks: int,
    weapon_profile: WeaponProfile,
    roll_id_prefix: str,
    attacker_player_id: str,
    defender_player_id: str,
    allocated_model_id: str,
    include_generated_hit: bool,
) -> tuple[DiceRollResult, ...]:
    hit_wound_results: list[DiceRollResult] = []
    save_results: list[DiceRollResult] = []
    for attack_index in range(attacks):
        attack_context_id = replace(
            attack_sequence,
            attack_index=attack_index,
        ).attack_context_id()
        suffix = f"{roll_id_prefix}-attack-{attack_index + 1}"
        hit_wound_results.extend(
            (
                _fixed_roll(
                    f"roll:{suffix}-hit",
                    attack_sequence_hit_roll_spec(
                        weapon_profile_id=weapon_profile.profile_id,
                        attack_context_id=attack_context_id,
                        attacker_player_id=attacker_player_id,
                    ),
                ),
                _fixed_roll(
                    f"roll:{suffix}-wound",
                    attack_sequence_wound_roll_spec(
                        weapon_profile_id=weapon_profile.profile_id,
                        attack_context_id=attack_context_id,
                        attacker_player_id=attacker_player_id,
                    ),
                ),
            )
        )
        save_results.append(
            _fixed_roll(
                f"roll:{suffix}-save",
                saving_throw_roll_spec(
                    save_kind=SaveKind.ARMOUR,
                    player_id=defender_player_id,
                    allocated_model_id=allocated_model_id,
                    attack_context_id=attack_context_id,
                ),
                value=1,
            )
        )
        if include_generated_hit:
            generated_context_id = f"{attack_context_id}:generated-hit-002"
            hit_wound_results.append(
                _fixed_roll(
                    f"roll:{suffix}-generated-wound",
                    attack_sequence_wound_roll_spec(
                        weapon_profile_id=weapon_profile.profile_id,
                        attack_context_id=generated_context_id,
                        attacker_player_id=attacker_player_id,
                    ),
                )
            )
            save_results.append(
                _fixed_roll(
                    f"roll:{suffix}-generated-save",
                    saving_throw_roll_spec(
                        save_kind=SaveKind.ARMOUR,
                        player_id=defender_player_id,
                        allocated_model_id=allocated_model_id,
                        attack_context_id=generated_context_id,
                    ),
                    value=1,
                )
            )
    return (*hit_wound_results, *save_results)


def drift_pending_destruction_reaction_payload(
    *,
    lifecycle_payload: dict[str, Any],
    attack_sequence: AttackSequence,
    drift_kind: str,
) -> None:
    pending = attack_sequence.pending_grouped_damage
    if pending is None or pending.next_index != 1:
        raise AssertionError("Drift regression requires the second grouped save die.")
    request_payload = lifecycle_payload["decisions"]["queue"]["pending_requests"][0]
    destruction_context = request_payload["payload"]["destruction_context"]
    provenance_payload = destruction_context["destruction_provenance"]
    provenance = DestructionProvenance.from_payload(provenance_payload)
    profile = provenance.source_weapon_profile
    if profile is None:
        raise AssertionError("Drift regression requires attack provenance.")
    if drift_kind in {"attack_context", "generated_hit_context"}:
        current_context = pending.sorted_save_dice[pending.next_index]["attack_context"]
        stale_context = pending.sorted_save_dice[0]["attack_context"]
        expected_current = (1, 0) if drift_kind == "attack_context" else (0, 1)
        if (
            current_context["attack_index"],
            current_context["generated_hit_index"],
        ) != expected_current:
            raise AssertionError("Drift regression current context is not the expected die.")
        if (stale_context["attack_index"], stale_context["generated_hit_index"]) != (0, 0):
            raise AssertionError("Drift regression stale context is not the initial hit.")
        destruction_context["attack_context"] = stale_context
        provenance_payload["attack_context_id"] = stale_context["attack_context_id"]
        return
    if drift_kind == "range":
        drifted = replace(profile, range_profile=RangeProfile.distance(12))
        provenance_payload["attack_kind"] = DestructionAttackKind.RANGED.value
    elif drift_kind == "damage":
        drifted = replace(profile, damage_profile=DamageProfile.fixed(1))
    elif drift_kind == "keywords":
        drifted = replace(profile, keywords=(WeaponKeyword.LETHAL_HITS,))
    elif drift_kind == "source_ids":
        drifted = replace(profile, source_ids=(*profile.source_ids, "test:provenance-drift"))
    else:
        raise AssertionError("Unsupported destruction-reaction drift kind.")
    provenance_payload["source_weapon_profile"] = drifted.to_payload()


def _fixed_roll(
    roll_id: str,
    spec: DiceRollSpec,
    *,
    value: int = 6,
) -> DiceRollResult:
    return DiceRollResult.from_values(
        roll_id=roll_id,
        spec=spec,
        values=(value,),
        source="fixed",
    )
