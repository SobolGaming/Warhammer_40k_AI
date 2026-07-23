from __future__ import annotations

from dataclasses import dataclass
from typing import Self, TypedDict

from warhammer40k_core.core.validation import IdentifierValidator
from warhammer40k_core.core.weapon_profiles import WeaponProfile, WeaponProfilePayload
from warhammer40k_core.engine.event_log import canonical_json
from warhammer40k_core.engine.phase import GameLifecycleError

POST_ROLL_ATTACK_PROFILE_POOLS_SOURCE_ID = (
    "gw-11e-rules-and-event-updates-2026-07-22:app-core-rules:05.03.02-post-roll-attack-profiles"
)


class PostRollModifiedAttackPayload(TypedDict):
    attack_context_id: str
    weapon_profile: WeaponProfilePayload


class PostRollAttackPoolPayload(TypedDict):
    pool_id: str
    weapon_profile: WeaponProfilePayload
    attack_context_ids: list[str]
    source_rule_id: str


class PostRollAttackPoolSetPayload(TypedDict):
    sequence_id: str
    active_player_id: str
    selected_pool: PostRollAttackPoolPayload | None
    unresolved_pools: list[PostRollAttackPoolPayload]


_validate_identifier = IdentifierValidator(GameLifecycleError)


@dataclass(frozen=True, slots=True)
class PostRollModifiedAttack:
    attack_context_id: str
    weapon_profile: WeaponProfile

    def __post_init__(self) -> None:
        object.__setattr__(
            self,
            "attack_context_id",
            _validate_identifier(
                "PostRollModifiedAttack attack_context_id", self.attack_context_id
            ),
        )
        if type(self.weapon_profile) is not WeaponProfile:
            raise GameLifecycleError("PostRollModifiedAttack requires a WeaponProfile.")

    def to_payload(self) -> PostRollModifiedAttackPayload:
        return {
            "attack_context_id": self.attack_context_id,
            "weapon_profile": self.weapon_profile.to_payload(),
        }

    @classmethod
    def from_payload(cls, payload: PostRollModifiedAttackPayload) -> Self:
        return cls(
            attack_context_id=payload["attack_context_id"],
            weapon_profile=WeaponProfile.from_payload(payload["weapon_profile"]),
        )


@dataclass(frozen=True, slots=True)
class PostRollAttackPool:
    pool_id: str
    weapon_profile: WeaponProfile
    attack_context_ids: tuple[str, ...]
    source_rule_id: str = POST_ROLL_ATTACK_PROFILE_POOLS_SOURCE_ID

    def __post_init__(self) -> None:
        object.__setattr__(
            self,
            "pool_id",
            _validate_identifier("PostRollAttackPool pool_id", self.pool_id),
        )
        if type(self.weapon_profile) is not WeaponProfile:
            raise GameLifecycleError("PostRollAttackPool requires a WeaponProfile.")
        context_ids = tuple(
            _validate_identifier("PostRollAttackPool attack_context_id", context_id)
            for context_id in self.attack_context_ids
        )
        if not context_ids or len(set(context_ids)) != len(context_ids):
            raise GameLifecycleError(
                "PostRollAttackPool attack_context_ids must be non-empty and unique."
            )
        object.__setattr__(self, "attack_context_ids", tuple(sorted(context_ids)))
        object.__setattr__(
            self,
            "source_rule_id",
            _validate_identifier("PostRollAttackPool source_rule_id", self.source_rule_id),
        )

    def to_payload(self) -> PostRollAttackPoolPayload:
        return {
            "pool_id": self.pool_id,
            "weapon_profile": self.weapon_profile.to_payload(),
            "attack_context_ids": list(self.attack_context_ids),
            "source_rule_id": self.source_rule_id,
        }

    @classmethod
    def from_payload(cls, payload: PostRollAttackPoolPayload) -> Self:
        return cls(
            pool_id=payload["pool_id"],
            weapon_profile=WeaponProfile.from_payload(payload["weapon_profile"]),
            attack_context_ids=tuple(payload["attack_context_ids"]),
            source_rule_id=payload["source_rule_id"],
        )


@dataclass(frozen=True, slots=True)
class PostRollAttackPoolSet:
    sequence_id: str
    active_player_id: str
    unresolved_pools: tuple[PostRollAttackPool, ...]
    selected_pool: PostRollAttackPool | None = None

    def __post_init__(self) -> None:
        object.__setattr__(
            self,
            "sequence_id",
            _validate_identifier("PostRollAttackPoolSet sequence_id", self.sequence_id),
        )
        object.__setattr__(
            self,
            "active_player_id",
            _validate_identifier("PostRollAttackPoolSet active_player_id", self.active_player_id),
        )
        if any(type(pool) is not PostRollAttackPool for pool in self.unresolved_pools):
            raise GameLifecycleError("PostRollAttackPoolSet unresolved_pools are invalid.")
        if self.selected_pool is not None and type(self.selected_pool) is not PostRollAttackPool:
            raise GameLifecycleError("PostRollAttackPoolSet selected_pool is invalid.")
        if not self.unresolved_pools and self.selected_pool is None:
            raise GameLifecycleError("PostRollAttackPoolSet requires an attack pool.")
        pools = (
            self.unresolved_pools
            if self.selected_pool is None
            else (self.selected_pool, *self.unresolved_pools)
        )
        pool_ids = tuple(pool.pool_id for pool in pools)
        if len(set(pool_ids)) != len(pool_ids):
            raise GameLifecycleError("PostRollAttackPoolSet pool IDs must be unique.")
        attack_context_ids = tuple(
            context_id for pool in pools for context_id in pool.attack_context_ids
        )
        if len(set(attack_context_ids)) != len(attack_context_ids):
            raise GameLifecycleError(
                "PostRollAttackPoolSet attack contexts cannot occur in multiple pools."
            )

    @classmethod
    def from_modified_attacks(
        cls,
        *,
        sequence_id: str,
        active_player_id: str,
        attacks: tuple[PostRollModifiedAttack, ...],
    ) -> Self:
        if not attacks or any(type(attack) is not PostRollModifiedAttack for attack in attacks):
            raise GameLifecycleError("Post-roll profile splitting requires modified attacks.")
        groups: dict[str, tuple[WeaponProfile, list[str]]] = {}
        for attack in attacks:
            signature = canonical_json(attack.weapon_profile.to_payload())
            stored = groups.get(signature)
            if stored is None:
                groups[signature] = (attack.weapon_profile, [attack.attack_context_id])
            else:
                stored[1].append(attack.attack_context_id)
        pools = tuple(
            PostRollAttackPool(
                pool_id=f"{sequence_id}:post-roll-pool-{index:03d}",
                weapon_profile=profile,
                attack_context_ids=tuple(context_ids),
            )
            for index, (_signature, (profile, context_ids)) in enumerate(
                sorted(groups.items()),
                start=1,
            )
        )
        return cls(
            sequence_id=sequence_id,
            active_player_id=active_player_id,
            unresolved_pools=pools,
        )

    @property
    def all_attack_context_ids(self) -> tuple[str, ...]:
        pools = (
            self.unresolved_pools
            if self.selected_pool is None
            else (self.selected_pool, *self.unresolved_pools)
        )
        return tuple(context_id for pool in pools for context_id in pool.attack_context_ids)

    def with_selected_pool(
        self,
        *,
        actor_id: str,
        selected_pool_id: str,
    ) -> Self:
        if self.selected_pool is not None:
            raise GameLifecycleError("Post-roll attack pool is already selected.")
        if _validate_identifier("actor_id", actor_id) != self.active_player_id:
            raise GameLifecycleError("Only the active player can order post-roll attack pools.")
        requested_pool_id = _validate_identifier("selected_pool_id", selected_pool_id)
        selected = next(
            (pool for pool in self.unresolved_pools if pool.pool_id == requested_pool_id),
            None,
        )
        if selected is None:
            raise GameLifecycleError("Selected post-roll attack pool is not unresolved.")
        remaining = tuple(pool for pool in self.unresolved_pools if pool != selected)
        return type(self)(
            sequence_id=self.sequence_id,
            active_player_id=self.active_player_id,
            unresolved_pools=remaining,
            selected_pool=selected,
        )

    def after_selected_pool(self) -> Self | None:
        if self.selected_pool is None:
            raise GameLifecycleError("Post-roll attack pool completion requires a selection.")
        if not self.unresolved_pools:
            return None
        return type(self)(
            sequence_id=self.sequence_id,
            active_player_id=self.active_player_id,
            unresolved_pools=self.unresolved_pools,
        )

    def to_payload(self) -> PostRollAttackPoolSetPayload:
        return {
            "sequence_id": self.sequence_id,
            "active_player_id": self.active_player_id,
            "selected_pool": (
                None if self.selected_pool is None else self.selected_pool.to_payload()
            ),
            "unresolved_pools": [pool.to_payload() for pool in self.unresolved_pools],
        }

    @classmethod
    def from_payload(cls, payload: PostRollAttackPoolSetPayload) -> Self:
        return cls(
            sequence_id=payload["sequence_id"],
            active_player_id=payload["active_player_id"],
            selected_pool=(
                None
                if payload["selected_pool"] is None
                else PostRollAttackPool.from_payload(payload["selected_pool"])
            ),
            unresolved_pools=tuple(
                PostRollAttackPool.from_payload(pool) for pool in payload["unresolved_pools"]
            ),
        )
