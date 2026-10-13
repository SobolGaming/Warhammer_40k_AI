"""Native identical-attack gathering with frozen rules and physical ownership.

The raw signature remains a physical signature. This owner establishes semantic
equivalence at the real gathering boundary. Future allocation/result-dependent
providers without a pre-roll applicability inventory retain physical groups;
their explicit boundaries are persisted, and their real consumers still run.
"""

from __future__ import annotations

import json
from dataclasses import dataclass, replace
from hashlib import sha256
from typing import TYPE_CHECKING, Self, TypedDict, cast

from warhammer40k_core.core.validation import IdentifierValidator
from warhammer40k_core.engine.attack_gathering_dependencies import AttackGatheringDependency
from warhammer40k_core.engine.event_log import (
    EventRecord,
    JsonValue,
    canonical_json,
    validate_json_value,
)
from warhammer40k_core.engine.phase import BattlePhase, GameLifecycleError

if TYPE_CHECKING:
    from warhammer40k_core.engine.allocated_attack_damage_modifiers import (
        AllocatedAttackDamageModifierBinding,
    )
    from warhammer40k_core.engine.attack_sequence_model import GatheredAttackGroup
    from warhammer40k_core.engine.attack_sequence_state import AttackSequence
    from warhammer40k_core.engine.decision_request import DecisionRequest
    from warhammer40k_core.engine.game_state import GameState
    from warhammer40k_core.engine.post_roll_weapon_profile_modifiers import (
        PostRollWeaponProfileModifierBinding,
    )
    from warhammer40k_core.engine.runtime_modifiers import (
        FailedSaveDamageReplacementBinding,
        RuntimeModifierRegistry,
        SaveOptionModifierBinding,
    )
    from warhammer40k_core.engine.weapon_declaration import RangedAttackPool

    type FutureBinding = (
        AllocatedAttackDamageModifierBinding
        | SaveOptionModifierBinding
        | PostRollWeaponProfileModifierBinding
        | FailedSaveDamageReplacementBinding
    )


class NativeAttackSnapshotPayload(TypedDict):
    pool_index: int
    attacker_model_instance_id: str
    source_phase: str
    battle_round: int
    pool_sha256: str
    raw_signature_json: str
    semantic_signature_json: str
    rules_json: str
    source_proof_json: str
    conservative_boundaries: list[str]


@dataclass(frozen=True, slots=True)
class NativeAttackSnapshot:
    pool_index: int
    attacker_model_instance_id: str
    source_phase: BattlePhase
    battle_round: int
    pool_sha256: str
    raw_signature_json: str
    semantic_signature_json: str
    rules_json: str
    source_proof_json: str
    conservative_boundaries: tuple[str, ...]

    def __post_init__(self) -> None:
        if type(self.pool_index) is not int or self.pool_index < 0:
            raise GameLifecycleError("Native attack snapshot requires a pool index.")
        if type(self.battle_round) is not int or self.battle_round < 1:
            raise GameLifecycleError("Native attack snapshot requires a battle round.")
        if type(self.source_phase) is not BattlePhase:
            raise GameLifecycleError("Native attack snapshot requires its source phase.")
        _identifier("snapshot attacker", self.attacker_model_instance_id)
        if (
            type(self.pool_sha256) is not str
            or len(self.pool_sha256) != 64
            or any(character not in "0123456789abcdef" for character in self.pool_sha256)
        ):
            raise GameLifecycleError("Native attack snapshot pool digest is invalid.")
        for value in (
            self.raw_signature_json,
            self.semantic_signature_json,
            self.rules_json,
            self.source_proof_json,
        ):
            _canonical_object(value)
        _digest_object(self.rules_json, "applicable_rules_sha256")
        _digest_object(self.source_proof_json, "source_proof_sha256")
        if type(self.conservative_boundaries) is not tuple:
            raise GameLifecycleError("Native gathering boundaries must be a tuple.")
        for boundary in self.conservative_boundaries:
            _identifier("native gathering boundary", boundary)
        if tuple(sorted(set(self.conservative_boundaries))) != self.conservative_boundaries:
            raise GameLifecycleError("Native gathering boundaries must be unique and ordered.")

    def equivalence_key(self) -> tuple[str, str, str]:
        # Physical identity is never discarded. It remains in the raw snapshot
        # and contribution, and remains a grouping boundary when proof is absent.
        return (
            self.semantic_signature_json
            if self.conservative_boundaries
            else "source-owned-signature",
            self.rules_json,
            self.attacker_model_instance_id if self.conservative_boundaries else "",
        )

    def validate_pool(self, pool: RangedAttackPool, *, target_has_character: bool) -> None:
        from warhammer40k_core.engine.attack_sequence_selection import identical_attack_signature

        if self.attacker_model_instance_id != pool.attacker_model_instance_id:
            raise GameLifecycleError("Native gathering snapshot physical bearer drift.")
        if self.pool_sha256 != _pool_digest(pool):
            raise GameLifecycleError("Native gathering snapshot physical pool drift.")
        if self.raw_signature_json != canonical_json(
            identical_attack_signature(pool, target_has_character=target_has_character).to_payload()
        ):
            raise GameLifecycleError("Native gathering snapshot raw signature drift.")
        if self.semantic_signature_json != _semantic_signature(
            pool, target_has_character=target_has_character
        ):
            raise GameLifecycleError("Native gathering snapshot semantic signature drift.")

    def to_payload(self) -> NativeAttackSnapshotPayload:
        return {
            "pool_index": self.pool_index,
            "attacker_model_instance_id": self.attacker_model_instance_id,
            "source_phase": self.source_phase.value,
            "battle_round": self.battle_round,
            "pool_sha256": self.pool_sha256,
            "raw_signature_json": self.raw_signature_json,
            "semantic_signature_json": self.semantic_signature_json,
            "rules_json": self.rules_json,
            "source_proof_json": self.source_proof_json,
            "conservative_boundaries": list(self.conservative_boundaries),
        }

    @classmethod
    def from_payload(cls, payload: NativeAttackSnapshotPayload) -> Self:
        if type(cast(object, payload)) is not dict or set(payload) != set(cls_payload_fields):
            raise GameLifecycleError("Native attack snapshot fields drift.")
        try:
            phase = BattlePhase(payload["source_phase"])
        except ValueError as error:
            raise GameLifecycleError("Native attack snapshot phase is unsupported.") from error
        if type(payload["conservative_boundaries"]) is not list:
            raise GameLifecycleError("Native attack snapshot boundaries must be a list.")
        return cls(
            pool_index=payload["pool_index"],
            attacker_model_instance_id=payload["attacker_model_instance_id"],
            source_phase=phase,
            battle_round=payload["battle_round"],
            pool_sha256=payload["pool_sha256"],
            raw_signature_json=payload["raw_signature_json"],
            semantic_signature_json=payload["semantic_signature_json"],
            rules_json=payload["rules_json"],
            source_proof_json=payload["source_proof_json"],
            conservative_boundaries=tuple(payload["conservative_boundaries"]),
        )


cls_payload_fields = frozenset(NativeAttackSnapshotPayload.__annotations__)
_identifier = IdentifierValidator(GameLifecycleError)


def validate_native_group_snapshots(group: GatheredAttackGroup) -> None:
    """Keep the model module within its existing budget and one shared proof."""
    if type(group.native_snapshots) is not tuple or any(
        type(snapshot) is not NativeAttackSnapshot for snapshot in group.native_snapshots
    ):
        raise GameLifecycleError("GatheredAttackGroup native snapshots must be typed.")
    if not group.native_snapshots:
        return
    if tuple(snapshot.pool_index for snapshot in group.native_snapshots) != group.pool_indices:
        raise GameLifecycleError("GatheredAttackGroup native snapshot indices drift.")
    first = group.native_snapshots[0]
    if first.raw_signature_json != canonical_json(group.signature.to_payload()):
        raise GameLifecycleError("GatheredAttackGroup primary native signature drift.")
    if any(
        snapshot.equivalence_key() != first.equivalence_key()
        or snapshot.source_phase is not first.source_phase
        or snapshot.battle_round != first.battle_round
        for snapshot in group.native_snapshots
    ):
        raise GameLifecycleError("GatheredAttackGroup native applicability drift.")


def native_gathered_attack_groups_for_target(
    *,
    state: GameState,
    registry: RuntimeModifierRegistry,
    attack_sequence: AttackSequence,
    target_unit_instance_id: str,
    target_has_character: bool,
    has_custom_callbacks: bool,
) -> tuple[GatheredAttackGroup, ...]:
    from warhammer40k_core.engine.attack_sequence_selection import (
        gathered_attack_groups_for_target,
    )

    used = set(attack_sequence.used_pool_indices)
    candidates = tuple(
        (index, pool)
        for index, pool in enumerate(attack_sequence.attack_pools)
        if index not in used and pool.target_unit_instance_id == target_unit_instance_id
    )
    # Existing same-bearer gathering is already proved by its raw signature.
    # It retains its exact payloads, roll scopes and synthetic pool authority.
    if len({pool.attacker_model_instance_id for _, pool in candidates}) < 2:
        return gathered_attack_groups_for_target(
            attack_sequence=attack_sequence,
            target_unit_instance_id=target_unit_instance_id,
            target_has_character=target_has_character,
        )
    snapshots: list[NativeAttackSnapshot] = []
    for index, pool in candidates:
        snapshot = native_attack_snapshot(
            state=state,
            registry=registry,
            sequence=attack_sequence,
            pool=pool,
            pool_index=index,
            target_has_character=target_has_character,
            has_custom_callbacks=has_custom_callbacks,
        )
        snapshots.append(snapshot)
    return groups_from_native_snapshots(
        attack_sequence=attack_sequence,
        target_unit_instance_id=target_unit_instance_id,
        target_has_character=target_has_character,
        snapshots=tuple(snapshots),
    )


def groups_from_native_snapshots(
    *,
    attack_sequence: AttackSequence,
    target_unit_instance_id: str,
    target_has_character: bool,
    snapshots: tuple[NativeAttackSnapshot, ...],
) -> tuple[GatheredAttackGroup, ...]:
    from warhammer40k_core.engine.attack_sequence_selection import (
        _gathered_attack_group_from_indices,
        identical_attack_signature,
    )

    used = set(attack_sequence.used_pool_indices)
    expected = tuple(
        index
        for index, pool in enumerate(attack_sequence.attack_pools)
        if index not in used and pool.target_unit_instance_id == target_unit_instance_id
    )
    if tuple(sorted(snapshot.pool_index for snapshot in snapshots)) != expected:
        raise GameLifecycleError(
            "Native gathering snapshots do not cover unresolved physical pools."
        )
    grouped: dict[tuple[str, str, str], list[NativeAttackSnapshot]] = {}
    for snapshot in sorted(snapshots, key=lambda item: item.pool_index):
        if snapshot.source_phase is not attack_sequence.source_phase:
            raise GameLifecycleError("Native gathering snapshot source phase drift.")
        snapshot.validate_pool(
            attack_sequence.attack_pools[snapshot.pool_index],
            target_has_character=target_has_character,
        )
        grouped.setdefault(snapshot.equivalence_key(), []).append(snapshot)
    groups: list[GatheredAttackGroup] = []
    for rows in grouped.values():
        snapshots = tuple(rows)
        indices = tuple(row.pool_index for row in snapshots)
        signature = identical_attack_signature(
            attack_sequence.attack_pools[indices[0]], target_has_character=target_has_character
        )
        group = _gathered_attack_group_from_indices(
            attack_sequence=attack_sequence,
            target_unit_instance_id=target_unit_instance_id,
            target_has_character=target_has_character,
            signature=signature,
            pool_indices=indices,
        )
        # Public group identity derives only from the existing physical group.
        # Internal rule fingerprints are separately authenticated in snapshots.
        groups.append(replace(group, native_snapshots=snapshots))
    return tuple(sorted(groups, key=lambda group: group.group_id))


def gathered_groups_for_pending_request(
    *,
    attack_sequence: AttackSequence,
    target_unit_instance_id: str,
    target_has_character: bool,
    request: DecisionRequest,
) -> tuple[GatheredAttackGroup, ...]:
    """Rebuild the trusted advertised boundary, never from a submitted cursor.

    Physical profiles/pools remain checked against current native ownership.
    The source-rule fingerprints are frozen at gathering, like the original
    target CHARACTER/visibility snapshot; later casualties cannot rewrite them.
    """
    from warhammer40k_core.engine.attack_sequence_model import (
        GatheredAttackGroup,
        GatheredAttackGroupPayload,
    )
    from warhammer40k_core.engine.attack_sequence_selection import gathered_attack_groups_for_target

    groups: list[GatheredAttackGroup] = []
    for option in request.options:
        if not isinstance(option.payload, dict):
            raise GameLifecycleError("Native gathering option must have an object payload.")
        raw = option.payload["gathered_group"]
        if not isinstance(raw, dict):
            raise GameLifecycleError("Native gathering option lacks its physical group.")
        groups.append(GatheredAttackGroup.from_payload(cast(GatheredAttackGroupPayload, raw)))
    if not any(group.native_snapshots for group in groups):
        return gathered_attack_groups_for_target(
            attack_sequence=attack_sequence,
            target_unit_instance_id=target_unit_instance_id,
            target_has_character=target_has_character,
        )
    if any(not group.native_snapshots for group in groups):
        raise GameLifecycleError("Native gathering options mix incompatible authority modes.")
    return groups_from_native_snapshots(
        attack_sequence=attack_sequence,
        target_unit_instance_id=target_unit_instance_id,
        target_has_character=target_has_character,
        snapshots=tuple(snapshot for group in groups for snapshot in group.native_snapshots),
    )


def native_context_pool(
    sequence: AttackSequence, context: dict[str, object]
) -> RangedAttackPool | None:
    """Authenticate a persisted physical occurrence without changing its cursor."""
    from warhammer40k_core.engine.attack_sequence_model import HitRoll
    from warhammer40k_core.engine.attack_sequence_selection import (
        _synthetic_pool_for_gathered_group,
    )

    group = sequence.current_gathered_group
    if group is None or not group.native_snapshots:
        return None
    index = context.get("attack_index")
    generated = context.get("generated_hit_index")
    if type(index) is not int or not 0 <= index < group.total_attacks:
        raise GameLifecycleError("Native persisted attack index is outside its physical group.")
    if type(generated) is not int or generated < 0:
        raise GameLifecycleError("Native persisted generated hit index is invalid.")
    expected_id = (
        f"{sequence.sequence_id}:pool-{sequence.pool_index + 1:03d}:attack-{index + 1:03d}"
    )
    if generated:
        hit = context.get("hit_roll")
        if not isinstance(hit, dict):
            raise GameLifecycleError("Native generated attack lacks its original hit.")
        from warhammer40k_core.engine.attack_sequence_model import HitRollPayload

        roll = HitRoll.from_payload(cast(HitRollPayload, hit))
        if not roll.successful or generated >= roll.generated_hits:
            raise GameLifecycleError("Native generated attack is outside its original hit.")
        expected_id += f":generated-hit-{generated + 1:03d}"
    pool = _synthetic_pool_for_gathered_group(
        gathered_group=group, attack_pools=sequence.attack_pools, attack_index=index
    )
    pool = _post_roll_pool_for_context(sequence, pool, expected_id)
    expected: dict[str, object] = {
        "sequence_id": sequence.sequence_id,
        "source_phase": sequence.source_phase.value,
        "pool_index": sequence.pool_index,
        "attack_context_id": expected_id,
        "attacker_player_id": sequence.attacker_player_id,
        "attacking_unit_instance_id": sequence.attacking_unit_instance_id,
        "attacker_model_instance_id": pool.attacker_model_instance_id,
        "weapon_instance_id": pool.weapon_instance_id,
        "weapon_profile_id": pool.weapon_profile_id,
        "target_unit_instance_id": pool.target_unit_instance_id,
        "selected_weapon_ability_ids": list(pool.selected_weapon_ability_ids),
    }
    if any(context.get(key) != value for key, value in expected.items()):
        raise GameLifecycleError("Native persisted attack physical occurrence drift.")
    return pool


def _post_roll_pool_for_context(
    sequence: AttackSequence, pool: RangedAttackPool, context_id: str
) -> RangedAttackPool:
    pools = sequence.post_roll_attack_pools
    if pools is None:
        return pool
    candidates = (*pools.unresolved_pools, *((pools.selected_pool,) if pools.selected_pool else ()))
    matches = [candidate for candidate in candidates if context_id in candidate.attack_context_ids]
    if len(matches) != 1:
        raise GameLifecycleError("Native modified occurrence lacks its unique post-roll pool.")
    profile = matches[0].weapon_profile
    return replace(pool, weapon_profile_id=profile.profile_id, weapon_profile=profile)


def native_pool_for_wound_occurrence(
    sequence: AttackSequence, events: tuple[EventRecord, ...], context_id: str
) -> RangedAttackPool:
    """Bind Save/Damage choices to a completed journal occurrence, not a cursor."""
    from warhammer40k_core.engine.attack_sequence_selection import (
        _synthetic_pool_for_gathered_group,
    )

    group = sequence.current_gathered_group
    if group is None or not group.native_snapshots:
        raise GameLifecycleError("Native wound occurrence requires its frozen group.")
    rows = [
        event.payload
        for event in events
        if event.event_type == "attack_sequence_step"
        and isinstance(event.payload, dict)
        and event.payload.get("sequence_id") == sequence.sequence_id
        and event.payload.get("pool_index") == sequence.pool_index
        and event.payload.get("step") == "wound"
        and event.payload.get("attack_context_id") == context_id
    ]
    if len(rows) != 1:
        raise GameLifecycleError("Native Save/Damage occurrence lacks its unique completed Wound.")
    index = rows[0].get("attack_index")
    wound = rows[0].get("payload")
    if (
        type(index) is not int
        or not 0 <= index < group.total_attacks
        or not isinstance(wound, dict)
        or wound.get("successful") is not True
    ):
        raise GameLifecycleError("Native Save/Damage occurrence lacks a successful physical Wound.")
    pool = _synthetic_pool_for_gathered_group(
        attack_pools=sequence.attack_pools, gathered_group=group, attack_index=index
    )
    if wound.get("weapon_profile_id") != pool.weapon_profile_id:
        raise GameLifecycleError("Native completed Wound physical profile drift.")
    return _post_roll_pool_for_context(sequence, pool, context_id)


def native_attack_snapshot(
    *,
    state: GameState,
    registry: RuntimeModifierRegistry,
    sequence: AttackSequence,
    pool: RangedAttackPool,
    pool_index: int,
    target_has_character: bool,
    has_custom_callbacks: bool,
) -> NativeAttackSnapshot:
    from warhammer40k_core.engine.attack_sequence_selection import identical_attack_signature
    from warhammer40k_core.engine.rules_units import rules_unit_view_by_id

    attacker = rules_unit_view_by_id(
        state=state, unit_instance_id=sequence.attacking_unit_instance_id
    )
    attacker.model_by_id(pool.attacker_model_instance_id)
    if attacker.owner_player_id != sequence.attacker_player_id:
        raise GameLifecycleError("Native gathering attacker ownership drift.")
    boundaries, inventory = _conservative_inventory(
        state=state,
        registry=registry,
        sequence=sequence,
        pool=pool,
        has_custom_callbacks=has_custom_callbacks,
    )
    rules: dict[str, JsonValue] = {"conservative_inventory": inventory}
    proof: dict[str, JsonValue] = {"conservative_inventory": inventory}
    if not boundaries:
        rules, proof = _current_applicable_rules(
            state=state,
            registry=registry,
            sequence=sequence,
            pool=pool,
            target_has_character=target_has_character,
        )
        rules["future_provider_dependencies"] = inventory
        proof["future_provider_dependencies"] = inventory
    return NativeAttackSnapshot(
        pool_index=pool_index,
        attacker_model_instance_id=pool.attacker_model_instance_id,
        source_phase=sequence.source_phase,
        battle_round=state.battle_round,
        pool_sha256=_pool_digest(pool),
        raw_signature_json=canonical_json(
            identical_attack_signature(pool, target_has_character=target_has_character).to_payload()
        ),
        semantic_signature_json=_semantic_signature(
            pool, target_has_character=target_has_character
        ),
        # Digests preserve equality/provenance without putting hidden source
        # conditions, resource inventories or target choices into public options.
        rules_json=canonical_json(
            {"applicable_rules_sha256": sha256(canonical_json(rules).encode()).hexdigest()}
        ),
        source_proof_json=canonical_json(
            {"source_proof_sha256": sha256(canonical_json(proof).encode()).hexdigest()}
        ),
        conservative_boundaries=boundaries,
    )


def _conservative_inventory(
    *,
    state: GameState,
    registry: RuntimeModifierRegistry,
    sequence: AttackSequence,
    pool: RangedAttackPool,
    has_custom_callbacks: bool,
) -> tuple[tuple[str, ...], dict[str, JsonValue]]:
    from warhammer40k_core.engine.native_gathering_numeric_rules import gathering_numeric_values
    from warhammer40k_core.engine.rules_unit_effects import rules_unit_effect_applications

    reasons: set[str] = set()
    if has_custom_callbacks:
        reasons.add("custom-attack-callback-applicability-unresolved")
    bindings: dict[str, tuple[FutureBinding, ...]] = {
        "allocated_damage": registry.allocated_attack_damage_modifier_bindings,
        "save_options": registry.save_option_modifier_bindings,
        "post_roll": registry.post_roll_weapon_profile_modifier_bindings,
        "failed_save_replacement": registry.failed_save_damage_replacement_bindings,
    }
    inventory: dict[str, JsonValue] = {}
    for family, sources in bindings.items():
        if any(
            source.gathering_dependency is AttackGatheringDependency.UNKNOWN for source in sources
        ):
            reasons.add(f"{family}-provider-preroll-applicability-unresolved")
        inventory[family] = [
            {
                "modifier_id": source.modifier_id,
                "source_id": source.source_id,
                "gathering_dependency": source.gathering_dependency.value,
                "attack_kind": (
                    pool.weapon_profile.range_profile.kind.value
                    if source.gathering_dependency
                    is AttackGatheringDependency.ATTACK_KIND_AND_TARGET
                    else None
                ),
            }
            for source in sources
        ]
    profile = pool.weapon_profile
    if (
        profile.damage_profile.dice_expression is not None
        and registry.damage_roll_modifier_bindings
    ):
        reasons.add("random-damage-provider-applicability-unresolved")
    strength, toughness, _descriptors = gathering_numeric_values(
        state=state, registry=registry, pool=pool
    )
    if (strength is None or toughness is None) and any(
        binding.gathering_handler is None for binding in registry.wound_roll_modifier_bindings
    ):
        reasons.add("numeric-wound-provider-template-unproved")
    effects = {
        application.effect.effect_id: application.effect
        for unit_id in (sequence.attacking_unit_instance_id, pool.target_unit_instance_id)
        for application in rules_unit_effect_applications(state, unit_id)
    }
    inventory["effects"] = [validate_json_value(effect.to_payload()) for effect in effects.values()]
    return tuple(sorted(reasons)), inventory


def _current_applicable_rules(
    *,
    state: GameState,
    registry: RuntimeModifierRegistry,
    sequence: AttackSequence,
    pool: RangedAttackPool,
    target_has_character: bool,
) -> tuple[dict[str, JsonValue], dict[str, JsonValue]]:
    from warhammer40k_core.engine.attack_modifier_snapshots import attack_modifier_snapshots
    from warhammer40k_core.engine.attack_sequence_hit_wound import _critical_wound_threshold
    from warhammer40k_core.engine.catalog_modifier_ignore import (
        ModifierIgnoreKind,
        modifier_ignore_sources_for_gathering,
    )
    from warhammer40k_core.engine.generic_rule_attack_hooks import _matching_generic_attack_effects
    from warhammer40k_core.engine.hit_thresholds import resolve_hit_thresholds
    from warhammer40k_core.engine.modifier_permission_context import ModifierPermissionAttackContext
    from warhammer40k_core.engine.native_gathering_numeric_rules import (
        gathering_numeric_values,
        wound_gathering_inventory,
    )
    from warhammer40k_core.engine.rules_units import rules_unit_view_by_id
    from warhammer40k_core.engine.runtime_modifiers import (
        HitRollMinimumUnmodifiedSuccessContext,
        unified_attack_reroll_permission_contexts_for_unit,
    )
    from warhammer40k_core.engine.weapon_abilities import (
        FIRE_OVERWATCH_RULE_ID,
        INDIRECT_FIRE_NO_HIT_REROLLS_RULE_ID,
        INDIRECT_FIRE_STATIONARY_VISIBLE_RULE_ID,
        INDIRECT_SHOOTING_POLICY,
        SNAP_SHOOTING_RULE_ID,
    )
    from warhammer40k_core.rules.rule_ir import RuleEffectKind

    profile = pool.weapon_profile
    unit_id = sequence.attacking_unit_instance_id
    strength, toughness, numeric_descriptors = gathering_numeric_values(
        state=state, registry=registry, pool=pool
    )
    symbolic = strength is None or toughness is None
    minimum = 2
    if {FIRE_OVERWATCH_RULE_ID, SNAP_SHOOTING_RULE_ID} & set(pool.targeting_rule_ids):
        minimum = 6
    elif INDIRECT_FIRE_NO_HIT_REROLLS_RULE_ID in pool.targeting_rule_ids:
        minimum = (
            INDIRECT_SHOOTING_POLICY.stationary_visible_minimum_unmodified_success
            if INDIRECT_FIRE_STATIONARY_VISIBLE_RULE_ID in pool.targeting_rule_ids
            else INDIRECT_SHOOTING_POLICY.minimum_unmodified_success
        )
    thresholds = resolve_hit_thresholds(
        HitRollMinimumUnmodifiedSuccessContext(
            state,
            sequence.source_phase,
            unit_id,
            pool.attacker_model_instance_id,
            pool.target_unit_instance_id,
            profile,
            pool.targeting_rule_ids,
            minimum,
        )
    )
    hit_snapshots = attack_modifier_snapshots(
        state=state,
        pool=pool,
        source_phase=sequence.source_phase,
        runtime_modifier_registry=registry,
    )
    rules: dict[str, JsonValue] = {
        "hit_modifiers": [validate_json_value(item.to_payload()) for item in hit_snapshots],
        "hit_thresholds": {
            "minimum_success": thresholds.minimum_success,
            "critical_threshold": thresholds.critical_threshold,
            "source_ids": list(thresholds.source_ids),
            "critical_is_threshold": thresholds.critical_is_threshold,
            "success_requires_exact": thresholds.success_requires_exact,
        },
        "numeric_descriptors": numeric_descriptors,
        "wound_modifiers": wound_gathering_inventory(
            state=state,
            registry=registry,
            sequence=sequence,
            pool=pool,
            strength=strength,
            toughness=toughness,
        ),
    }
    wound_threshold = _critical_wound_threshold(
        state=state,
        pool=pool,
        source_phase=sequence.source_phase,
        target_keywords=rules_unit_view_by_id(
            state=state, unit_instance_id=pool.target_unit_instance_id
        ).keywords,
    )
    rules["wound_threshold"] = {
        "value": wound_threshold.value,
        "inclusive": wound_threshold.inclusive,
    }
    generic_sources = tuple(
        effect
        for kind in (
            RuleEffectKind.MODIFY_CHARACTERISTIC,
            RuleEffectKind.MODIFY_DICE_ROLL,
            RuleEffectKind.GRANT_ABILITY,
            RuleEffectKind.REROLL_PERMISSION,
            RuleEffectKind.SET_CONTEXTUAL_STATUS,
            RuleEffectKind.SET_CHARACTERISTIC,
            RuleEffectKind.GRANT_WEAPON_ABILITY,
            RuleEffectKind.OVERRIDE_DICE_ROLL_RESULT,
        )
        for effect in _matching_generic_attack_effects(
            state=state,
            attacking_unit_instance_id=unit_id,
            attacker_model_instance_id=pool.attacker_model_instance_id,
            target_unit_instance_id=pool.target_unit_instance_id,
            source_phase=sequence.source_phase,
            effect_kind=kind,
            legacy_attacker_role_allowed=lambda _effect: True,
            legacy_target_role_allowed=lambda _effect: True,
            weapon_profile=profile,
            attack_strength=strength,
            target_toughness=toughness,
            gathering_templates=symbolic,
        )
    )
    from warhammer40k_core.engine.native_gathering_permission_relevance import (
        generic_source_inventory,
        unused_attack_characteristic_sources,
        unused_attacker_ignore_sources,
        unused_fixed_damage_roll_sources,
    )

    rules["generic_applicable_sources"] = cast(
        list[JsonValue], [generic_source_inventory(effect) for effect in generic_sources]
    )
    # The actual Damage owner consumes roll modifiers only after a random
    # Damage roll. Fixed Damage has no roll; random Damage has no scalar yet.
    # Matched generic sources retain the future random-roll inventory below.
    rules["damage_modifiers"] = []
    for label in ("hit", "wound"):
        roll_type = f"attack_sequence.{label}"
        rules[f"{label}_rerolls"] = [
            {
                "permission": validate_json_value(context.permission.to_payload()),
                "source_payload": context.source_payload,
            }
            for context in unified_attack_reroll_permission_contexts_for_unit(
                state=state,
                player_id=sequence.attacker_player_id,
                attacking_unit_instance_id=unit_id,
                attacker_model_instance_id=pool.attacker_model_instance_id,
                target_unit_instance_id=pool.target_unit_instance_id,
                source_phase=sequence.source_phase,
                attack_kind="ranged" if sequence.source_phase is BattlePhase.SHOOTING else "melee",
                roll_type=roll_type,
                registry=registry,
                weapon_profile=profile,
                shooting_type=pool.shooting_type,
            )
        ]
    raw_permissions: list[JsonValue] = []
    semantic_permissions: list[JsonValue] = []
    raw_persisted_sources: list[JsonValue] = []
    semantic_persisted_sources: list[JsonValue] = []
    from warhammer40k_core.engine.native_gathering_permission_relevance import (
        attacker_permission_kinds_for_gathering,
    )

    active_attacker_kinds = attacker_permission_kinds_for_gathering(
        state=state,
        registry=registry,
        attacking_unit_instance_id=unit_id,
        pool=pool,
        hit_snapshots=hit_snapshots,
        wound_inventory=cast(list[JsonValue], rules["wound_modifiers"]),
        generic_sources=generic_sources,
    )
    for kind in active_attacker_kinds:
        sources = modifier_ignore_sources_for_gathering(
            state=state,
            ability_index=registry.modifier_permission_index(sequence.attacker_player_id),
            unit_instance_id=unit_id,
            kind=kind,
            model_instance_id=pool.attacker_model_instance_id,
            weapon_profile_id=pool.weapon_profile_id,
            attack_context=ModifierPermissionAttackContext(
                unit_id,
                pool.attacker_model_instance_id,
                pool.target_unit_instance_id,
                "attacker",
                sequence.source_phase,
                profile,
                None
                if kind
                in {
                    ModifierIgnoreKind.HIT_ROLL,
                    ModifierIgnoreKind.BALLISTIC_SKILL_CHARACTERISTIC,
                    ModifierIgnoreKind.WEAPON_SKILL_CHARACTERISTIC,
                }
                else strength,
                None
                if kind
                in {
                    ModifierIgnoreKind.HIT_ROLL,
                    ModifierIgnoreKind.BALLISTIC_SKILL_CHARACTERISTIC,
                    ModifierIgnoreKind.WEAPON_SKILL_CHARACTERISTIC,
                }
                else toughness,
            ),
        )
        raw_persisted_sources.extend(row.raw_payload for row in sources.persisted_source_templates)
        semantic_persisted_sources.extend(
            row.comparison_payload for row in sources.persisted_source_templates
        )
        for permission in sources.catalog_permissions:
            raw = cast(dict[str, JsonValue], validate_json_value(permission.to_payload()))
            raw_permissions.append({"kind": kind.value, "permission": raw})
            source_context = permission.source_context
            semantic_context = (
                None
                if source_context is None
                else {
                    key: value
                    for key, value in cast(dict[str, JsonValue], source_context).items()
                    if key
                    not in {
                        "subject_model_instance_id",
                        "subject_weapon_profile_id",
                        "subject_component_unit_instance_id",
                    }
                }
            )
            semantic_permissions.append(
                {
                    "kind": kind.value,
                    "permission": {**raw, "source_context": semantic_context},
                }
            )
    rules["ignore_permissions"] = semantic_permissions
    rules["persisted_attacker_ignore_sources"] = semantic_persisted_sources
    from warhammer40k_core.engine.damage_allocation import allocation_context_for_unit

    target = rules_unit_view_by_id(state=state, unit_instance_id=pool.target_unit_instance_id)
    candidates = allocation_context_for_unit(
        state=state, target_unit_instance_id=pool.target_unit_instance_id
    ).alive_model_ids
    from warhammer40k_core.engine.native_gathering_permission_relevance import (
        target_permission_kinds_for_gathering,
    )

    target_permissions: list[JsonValue] = []
    raw_target_sources: list[JsonValue] = []
    semantic_target_sources: list[JsonValue] = []
    for model_id in candidates:
        for kind in target_permission_kinds_for_gathering(
            state=state, registry=registry, pool=pool, model_instance_id=model_id
        ):
            sources = modifier_ignore_sources_for_gathering(
                state=state,
                ability_index=registry.modifier_permission_index(target.owner_player_id),
                unit_instance_id=target.unit_instance_id,
                kind=kind,
                model_instance_id=model_id,
                attack_context=ModifierPermissionAttackContext(
                    unit_id,
                    pool.attacker_model_instance_id,
                    pool.target_unit_instance_id,
                    "target",
                    sequence.source_phase,
                    profile,
                    strength,
                    toughness,
                ),
            )
            target_permissions.extend(
                {
                    "candidate_model_instance_id": model_id,
                    "kind": kind.value,
                    "permission": validate_json_value(permission.to_payload()),
                }
                for permission in sources.catalog_permissions
            )
            raw_target_sources.extend(row.raw_payload for row in sources.persisted_source_templates)
            semantic_target_sources.extend(
                row.comparison_payload for row in sources.persisted_source_templates
            )
    rules["target_model_ignore_permissions"] = target_permissions
    rules["target_model_ignore_source_templates"] = semantic_target_sources
    rules["dice_override_sources"] = _dice_override_sources(
        state=state, sequence=sequence, pool=pool
    )
    proof: dict[str, JsonValue] = {
        **rules,
        "ignore_permissions": raw_permissions,
        "persisted_attacker_ignore_sources": raw_persisted_sources,
        "target_model_ignore_source_templates": raw_target_sources,
    }
    from warhammer40k_core.engine.native_gathering_cover_rules import (
        compare_cover_modifier,
        cover_gathering_inventories,
    )

    cover_raw, cover_applicable = cover_gathering_inventories(
        state=state, pool=pool, registry=registry
    )
    proof["cover_sources"] = cover_raw
    # Keep the physical snapshot untouched; comparison receives its own deep copy.
    comparison = cast(dict[str, JsonValue], json.loads(canonical_json(rules)))
    unused_grants = unused_attacker_ignore_sources(
        effects=generic_sources, active_kinds=active_attacker_kinds
    )
    proof["unused_ignore_grants_excluded_from_comparison"] = cast(list[JsonValue], unused_grants)
    unused_characteristics = unused_attack_characteristic_sources(generic_sources, pool=pool)
    if unused_characteristics:
        proof["unused_characteristic_sources_excluded_from_comparison"] = cast(
            list[JsonValue], unused_characteristics
        )
    unused_damage_rolls = unused_fixed_damage_roll_sources(generic_sources, pool=pool)
    if unused_damage_rolls:
        proof["unused_fixed_damage_roll_sources_excluded_from_comparison"] = cast(
            list[JsonValue], unused_damage_rolls
        )
    unused_keys = {
        canonical_json(row)
        for row in (*unused_grants, *unused_characteristics, *unused_damage_rolls)
    }
    comparison["generic_applicable_sources"] = [
        row
        for row in cast(list[JsonValue], comparison["generic_applicable_sources"])
        if canonical_json(row) not in unused_keys
    ]
    comparison["semantic_signature"] = _canonical_object(
        _semantic_signature(pool, target_has_character=target_has_character)
    )
    from warhammer40k_core.engine.shooting_targets import BENEFIT_OF_COVER_RULE_ID

    if any(
        item.kind == "skill" and item.modifier.source_id == BENEFIT_OF_COVER_RULE_ID
        for item in hit_snapshots
    ):
        comparison["cover_sources"] = cover_applicable
        compare_cover_modifier(comparison, raw=cover_raw, applicable=cover_applicable)
    from warhammer40k_core.engine.native_gathering_subject_rules import subject_rule_comparison

    return subject_rule_comparison(
        comparison,
        pool=pool,
        effects=generic_sources,
        attacker_model_instance_id=pool.attacker_model_instance_id,
        source_component_unit_instance_id=rules_unit_view_by_id(
            state=state, unit_instance_id=unit_id
        ).component_unit_id_for_model(pool.attacker_model_instance_id),
    ), proof


def _dice_override_sources(
    *, state: GameState, sequence: AttackSequence, pool: RangedAttackPool
) -> list[JsonValue]:
    from warhammer40k_core.engine.dice_result_override_descriptors import (
        dice_result_override_descriptors_for_abilities,
    )
    from warhammer40k_core.engine.rules_units import rules_unit_view_by_id
    from warhammer40k_core.engine.unit_resource_state import unit_resource_total

    unit = rules_unit_view_by_id(state=state, unit_instance_id=sequence.attacking_unit_instance_id)
    model = unit.model_by_id(pool.attacker_model_instance_id)
    result: list[JsonValue] = []
    for component in unit.components:
        if not any(member.is_alive for member in component.unit.own_models):
            continue
        for descriptor in dice_result_override_descriptors_for_abilities(
            component.unit.datasheet_abilities
        ):
            if any(keyword in model.keywords for keyword in descriptor.excluded_model_keywords):
                continue
            count = unit_resource_total(
                state=state,
                unit_instance_id=component.unit.unit_instance_id,
                resource_kind=descriptor.resource_kind,
            )
            if count < descriptor.resource_cost:
                continue
            result.append(
                {
                    "source_component_unit_instance_id": component.unit.unit_instance_id,
                    "descriptor_id": descriptor.descriptor_id,
                    "source_rule_id": descriptor.source_rule_id,
                    "roll_types": list(descriptor.roll_types),
                    "replacement_value": descriptor.replacement_value,
                    "resource_kind": descriptor.resource_kind,
                    "resource_cost": descriptor.resource_cost,
                    "current_count": count,
                }
            )
    return result


def _semantic_signature(pool: RangedAttackPool, *, target_has_character: bool) -> str:
    from warhammer40k_core.engine.attack_sequence_selection import identical_attack_signature

    raw = dict(
        identical_attack_signature(pool, target_has_character=target_has_character).to_payload()
    )
    del raw["attacker_model_instance_id"]
    tokens = [
        token
        for token in cast(list[str], raw["weapon_rule_tokens"])
        if not token.startswith(("selected-weapon-ability:", "random-profile-weapon:"))
    ]
    selected = tuple(
        token.removeprefix("selected-weapon-ability:")
        for token in cast(list[str], raw["weapon_rule_tokens"])
        if token.startswith("selected-weapon-ability:")
    )
    if selected:
        context = pool.weapon_selection_context
        if context is None:
            raise GameLifecycleError("Native selected source requires physical source inventory.")
        sources = {
            source.instance_id: source for _, group in context.instance_groups() for source in group
        }
        for identifier in selected:
            source = sources[identifier]
            # Only a typed source owned by this exact weapon has a replaceable
            # physical subject. External grant ownership remains a distinction.
            owner = (
                "selected-physical-weapon"
                if source.owner_id == pool.weapon_instance_id
                else source.owner_id
            )
            tokens.append(
                "selected-weapon-source:"
                + canonical_json(
                    {
                        "owner_id": owner,
                        "source_id": source.source_id,
                        "source_instance_id": source.source_instance_id,
                        "slot_id": source.slot_id,
                        "ability_id": source.ability_id,
                    }
                )
            )
    raw["weapon_rule_tokens"] = sorted(tokens)
    return canonical_json(raw)


def _pool_digest(pool: RangedAttackPool) -> str:
    return sha256(canonical_json(pool.to_payload()).encode()).hexdigest()


def _canonical_object(value: str) -> dict[str, JsonValue]:
    if type(value) is not str:
        raise GameLifecycleError("Native snapshot requires canonical JSON strings.")
    try:
        parsed = validate_json_value(json.loads(value))
    except json.JSONDecodeError as error:
        raise GameLifecycleError("Native snapshot JSON is malformed.") from error
    if not isinstance(parsed, dict) or canonical_json(parsed) != value:
        raise GameLifecycleError("Native snapshot JSON object is not canonical.")
    return parsed


def _digest_object(value: str, key: str) -> None:
    parsed = _canonical_object(value)
    digest = parsed.get(key)
    if (
        set(parsed) != {key}
        or type(digest) is not str
        or len(digest) != 64
        or any(character not in "0123456789abcdef" for character in digest)
    ):
        raise GameLifecycleError("Native snapshot source fingerprint is malformed.")
