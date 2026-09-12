"""Canonical Order 40 model, geometry and persisted-grant fixtures."""

from __future__ import annotations

from dataclasses import replace
from typing import TYPE_CHECKING

from tests.core_stratagem_helpers import _replace_unit_poses
from tests.generic_modifier_helpers import generic_effect
from tests.phase13b_shooting_declaration_helpers import (
    _attack_pool_for_test,
    _canonical_catalog,
    _compact_intercessor_catalog,
    _first_weapon_profile,
    _shooting_lifecycle,
)
from warhammer40k_core.engine.effects import PersistingEffect
from warhammer40k_core.engine.lifecycle import GameLifecycle
from warhammer40k_core.engine.unit_factory import UnitInstance
from warhammer40k_core.engine.weapon_declaration import RangedAttackPool
from warhammer40k_core.geometry.pose import Pose


def smoke_scene(
    *, smoke_y: float = 10
) -> tuple[GameLifecycle, dict[str, UnitInstance], RangedAttackPool]:
    catalog = _compact_intercessor_catalog(_canonical_catalog())
    catalog = replace(
        catalog,
        datasheets=tuple(
            replace(
                sheet,
                keywords=replace(sheet.keywords, keywords=(*sheet.keywords.keywords, "SMOKE")),
            )
            for sheet in catalog.datasheets
        ),
    )
    lifecycle, units = _shooting_lifecycle(
        alpha_unit_ids=("attacker",),
        alpha_unit_specs=(
            ("attacker", "core-intercessor-like-infantry", "core-intercessor-like", 1),
        ),
        enemy_unit_specs=tuple(
            (key, "core-intercessor-like-infantry", "core-intercessor-like", 1)
            for key in ("smoke", "target")
        ),
        catalog=catalog,
        game_id="order40-smokescreen",
    )
    state = lifecycle.state
    assert state is not None
    for key, x, y in (("attacker", 10, 10), ("smoke", 20, smoke_y), ("target", 30, 10)):
        _replace_unit_poses(
            state, unit_instance_id=units[key].unit_instance_id, poses=(Pose.at(x, y),)
        )
    pool = _attack_pool_for_test(
        attacker=units["attacker"],
        defender=units["target"],
        weapon_profile=_first_weapon_profile(lifecycle, units["attacker"]),
        attacks=1,
    )
    return lifecycle, units, pool


def smoke_grant(unit_id: str, *, effect_id: str = "order40:cover") -> PersistingEffect:
    return replace(
        generic_effect(
            effect_id=effect_id,
            owner_player_id="player-b",
            target_unit_instance_ids=(unit_id,),
            target_kind="this_unit",
            effect_kind="grant_ability",
            parameters={"ability": "cover_from_obscuring_models"},
        ),
        source_rule_id="gw-11e-core-stratagems:core:smokescreen",
    )


if TYPE_CHECKING:
    from warhammer40k_core.adapters.local_session import LocalGameSession


def smoke_session() -> tuple[LocalGameSession, dict[str, UnitInstance], RangedAttackPool]:
    from warhammer40k_core.adapters.local_session import LocalGameSession
    from warhammer40k_core.engine.command_points import CommandPointSourceKind

    lifecycle, units, pool = smoke_scene(smoke_y=10.5)
    state = lifecycle.state
    assert state is not None
    # Both players can afford the rule; only the opponent may use it at this boundary.
    for player_id in state.player_ids:
        state.gain_command_points(
            player_id=player_id,
            amount=2,
            source_id=f"order40:fixture-cp:{player_id}",
            source_kind=CommandPointSourceKind.COMMAND_PHASE_START,
        )
    return (
        LocalGameSession(lifecycle=GameLifecycle.from_payload(lifecycle.to_payload())),
        units,
        pool,
    )
