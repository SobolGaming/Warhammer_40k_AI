"""Authenticate random weapon evaluations against accepted physical-weapon pools."""

from __future__ import annotations

import re
from dataclasses import replace
from typing import cast

from warhammer40k_core.core.army_catalog import ArmyCatalog
from warhammer40k_core.core.attributes import Characteristic
from warhammer40k_core.core.dice import (
    RandomCharacteristicRoll,
    RandomCharacteristicRollPayload,
    RandomCharacteristicTiming,
)
from warhammer40k_core.core.random_profile_values import (
    RandomProfileValue,
    RandomProfileValuePayload,
)
from warhammer40k_core.core.weapon_profiles import WeaponProfile
from warhammer40k_core.engine.decision_record import DecisionRecord
from warhammer40k_core.engine.event_log import EventRecord, JsonValue, canonical_json
from warhammer40k_core.engine.phase import GameLifecycleError
from warhammer40k_core.engine.post_roll_attack_profiles import (
    PostRollAttackPoolSet,
    PostRollAttackPoolSetPayload,
)
from warhammer40k_core.engine.random_attack_authority import validate_generated_profile_attack
from warhammer40k_core.engine.random_profile_roll_authority import validate_profile_roll
from warhammer40k_core.engine.weapon_declaration import RangedAttackPool, RangedAttackPoolPayload
from warhammer40k_core.rules.source_packages.warhammer_40000_11th import (
    core_random_profiles_2026_09 as random_source,
)

_EVENT = "random_weapon_profile_evaluated"
_FIELDS = frozenset(
    {
        "source_rule_id",
        "scope_id",
        "attack_context_id",
        "target_unit_instance_id",
        "wargear_id",
        "player_id",
        "model_instance_id",
        "weapon_instance_id",
        "weapon_profile_id",
        "descriptor",
        "roll",
    }
)


def validate_random_weapon_history(
    *,
    catalog: ArmyCatalog | None,
    event_records: tuple[EventRecord, ...],
    decision_records: tuple[DecisionRecord, ...],
) -> None:
    if not any(event.event_type == _EVENT for event in event_records):
        return
    if catalog is None:
        raise GameLifecycleError("Random weapon restore requires its authoritative catalog.")
    declarations: dict[str, tuple[str, tuple[RangedAttackPool, ...]]] = {}
    post_roll_profiles: dict[str, WeaponProfile] = {}
    decisions = {record.result.result_id: record for record in decision_records}
    physical_rolls: dict[str, JsonValue] = {}
    random_rolls: set[str] = set()
    seen: set[str] = set()
    for event_index, event in enumerate(event_records):
        body = event.payload
        if not isinstance(body, dict):
            if event.event_type == _EVENT:
                raise GameLifecycleError("Random weapon evaluation payload is invalid.")
            continue
        if event.event_type in {
            "shooting_declaration_accepted",
            "out_of_phase_shooting_declaration_accepted",
            "melee_declaration_accepted",
        }:
            raw_pools = body.get("attack_pools")
            if raw_pools is None and event.event_type == "melee_declaration_accepted":
                continue
            result_id = body.get("result_id")
            record = decisions.get(result_id) if isinstance(result_id, str) else None
            sequence_id = (
                body.get("attack_sequence_id")
                if event.event_type != "shooting_declaration_accepted"
                else f"attack-sequence:{result_id}"
            )
            if (
                record is None
                or record.result.actor_id is None
                or record.request.request_id != body.get("request_id")
                or type(sequence_id) is not str
                or not isinstance(raw_pools, list)
            ):
                raise GameLifecycleError("Random weapon declaration lacks its accepted decision.")
            if any(not isinstance(pool, dict) for pool in raw_pools):
                raise GameLifecycleError("Random weapon declaration pools are invalid.")
            declarations[sequence_id] = (
                record.result.actor_id,
                tuple(
                    RangedAttackPool.from_payload(cast(RangedAttackPoolPayload, pool))
                    for pool in raw_pools
                ),
            )
        elif event.event_type == "target_replacement_resolved":
            context = body.get("context")
            sequence_id = context.get("action_id") if isinstance(context, dict) else None
            if type(sequence_id) is str and sequence_id in declarations:
                raw_pools = body.get("attack_pools")
                if not isinstance(raw_pools, list) or any(
                    not isinstance(pool, dict) for pool in raw_pools
                ):
                    raise GameLifecycleError("Random weapon replacement pools are invalid.")
                declarations[sequence_id] = (
                    declarations[sequence_id][0],
                    tuple(
                        RangedAttackPool.from_payload(cast(RangedAttackPoolPayload, pool))
                        for pool in raw_pools
                    ),
                )
        elif event.event_type == "post_roll_attack_pools_created":
            raw = body.get("post_roll_attack_pools")
            if not isinstance(raw, dict):
                raise GameLifecycleError("Post-roll weapon evidence is invalid.")
            pool_set = PostRollAttackPoolSet.from_payload(cast(PostRollAttackPoolSetPayload, raw))
            for post_pool in pool_set.unresolved_pools:
                for post_attack_id in post_pool.attack_context_ids:
                    post_roll_profiles[post_attack_id] = post_pool.weapon_profile
        elif event.event_type == "dice_rolled":
            roll_id = body.get("roll_id")
            if isinstance(roll_id, str):
                physical_rolls[roll_id] = body
        elif event.event_type == "random_characteristic_rolled":
            random_rolls.add(canonical_json(body))
        elif event.event_type == _EVENT:
            if (
                frozenset(body) != _FIELDS
                or body["source_rule_id"] != random_source.RANDOM_PROFILES_SOURCE_ID
            ):
                raise GameLifecycleError("Random weapon evaluation shape or authority drifted.")
            scope, attack_id, actor = body["scope_id"], body["attack_context_id"], body["player_id"]
            if (
                type(scope) is not str
                or type(attack_id) is not str
                or type(actor) is not str
                or scope in seen
            ):
                raise GameLifecycleError("Random weapon occurrence is invalid or duplicated.")
            seen.add(scope)
            raw_value, raw_roll = body["descriptor"], body["roll"]
            if not isinstance(raw_value, dict) or not isinstance(raw_roll, dict):
                raise GameLifecycleError("Random weapon value or dice evidence is invalid.")
            value = RandomProfileValue.from_payload(cast(RandomProfileValuePayload, raw_value))
            if value.evaluation is not None:
                raise GameLifecycleError("Random weapon source descriptor must be unresolved.")
            roll = RandomCharacteristicRoll.from_payload(
                cast(RandomCharacteristicRollPayload, raw_roll)
            )
            sequence_id, pool_index, attack_index, generated = _attack_identity(attack_id)
            validate_generated_profile_attack(
                sequence_id=sequence_id,
                pool_index=pool_index,
                attack_index=attack_index,
                generated_hit_number=generated,
                events=event_records[:event_index],
            )
            if generated is not None and value.characteristic in {
                Characteristic.BALLISTIC_SKILL,
                Characteristic.WEAPON_SKILL,
            }:
                raise GameLifecycleError("Generated hits cannot reevaluate weapon Skill.")
            declaration = declarations.get(sequence_id)
            if declaration is None or declaration[0] != actor or pool_index >= len(declaration[1]):
                raise GameLifecycleError("Random weapon occurrence lacks its accepted attack.")
            pool = declaration[1][pool_index]
            if (
                attack_index >= pool.attacks
                or any(
                    body[key] != expected
                    for key, expected in (
                        ("weapon_instance_id", pool.weapon_instance_id),
                        ("model_instance_id", pool.attacker_model_instance_id),
                        ("weapon_profile_id", pool.weapon_profile_id),
                        ("wargear_id", pool.wargear_id),
                        ("target_unit_instance_id", pool.target_unit_instance_id),
                    )
                )
                or scope != f"{attack_id}:{pool.weapon_instance_id}:{value.characteristic.value}"
            ):
                raise GameLifecycleError("Random weapon physical identity or occurrence drifted.")
            profile = (
                post_roll_profiles.get(attack_id, pool.weapon_profile)
                if value.characteristic is Characteristic.ARMOR_PENETRATION
                else pool.weapon_profile
            )
            if _profile_value(profile, value.characteristic) != value:
                raise GameLifecycleError("Random weapon descriptor or bound modifiers drifted.")
            sources = [
                profile
                for item in catalog.wargear
                if item.wargear_id == pool.wargear_id
                for profile in item.weapon_profiles
                if profile.profile_id == pool.weapon_profile_id
            ]
            if len(sources) != 1 or replace(value, modifiers=()) != _profile_value(
                sources[0], value.characteristic
            ):
                raise GameLifecycleError("Random weapon descriptor lacks its catalog source.")
            validate_profile_roll(
                roll=roll,
                value=value,
                scope_id=scope,
                timing=RandomCharacteristicTiming.PER_WEAPON,
                actor_id=actor,
                reason=f"Weapon profile {value.characteristic.value}",
                physical_rolls=physical_rolls,
                random_rolls=random_rolls,
            )


def _profile_value(profile: WeaponProfile, characteristic: Characteristic) -> RandomProfileValue:
    values = (profile.skill, profile.strength, profile.armor_penetration)
    found = [value for value in values if value.characteristic is characteristic]
    if len(found) != 1 or not isinstance(found[0], RandomProfileValue):
        raise GameLifecycleError("Random weapon characteristic is absent from its profile.")
    return found[0]


def _attack_identity(value: str) -> tuple[str, int, int, int | None]:
    match = re.fullmatch(r"(.+):pool-([0-9]+):attack-([0-9]+)(?::generated-hit-([0-9]+))?", value)
    if (
        match is None
        or int(match[2]) < 1
        or int(match[3]) < 1
        or (match[4] is not None and int(match[4]) < 2)
    ):
        raise GameLifecycleError("Random weapon attack occurrence is invalid.")
    return (
        match[1],
        int(match[2]) - 1,
        int(match[3]) - 1,
        (None if match[4] is None else int(match[4])),
    )
