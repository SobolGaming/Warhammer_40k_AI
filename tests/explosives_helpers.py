"""Canonical Order 41 source-model and target scene."""

from dataclasses import replace

from tests.core_stratagem_helpers import _replace_unit_poses
from tests.phase13b_shooting_declaration_helpers import (
    _canonical_catalog,
    _compact_intercessor_catalog,
    _shooting_lifecycle,
)
from warhammer40k_core.engine.command_points import CommandPointSourceKind
from warhammer40k_core.engine.lifecycle import GameLifecycle
from warhammer40k_core.engine.list_validation import AttachmentDeclaration
from warhammer40k_core.engine.unit_factory import UnitInstance
from warhammer40k_core.geometry.pose import Pose


def explosives_scene(
    *,
    keyword: str = "GRENADES",
    target_x: float = 17,
    attached: bool = False,
    extra_friendly: bool = False,
) -> tuple[GameLifecycle, dict[str, UnitInstance]]:
    catalog = _compact_intercessor_catalog(_canonical_catalog())
    catalog = replace(
        catalog,
        datasheets=tuple(
            replace(
                sheet,
                keywords=replace(
                    sheet.keywords, keywords=tuple(sorted(set(sheet.keywords.keywords) | {keyword}))
                ),
            )
            for sheet in catalog.datasheets
        ),
    )
    lifecycle, units = _shooting_lifecycle(
        alpha_unit_ids=(("source", "leader") if attached else ("source",))
        + ("other",) * extra_friendly,
        alpha_unit_specs=(("source", "core-intercessor-like-infantry", "core-intercessor-like", 2),)
        + (("leader", "core-character-leader", "core-character-leader", 1),) * attached
        + (("other", "core-intercessor-like-infantry", "core-intercessor-like", 1),)
        * extra_friendly,
        alpha_attachment_declarations=(
            AttachmentDeclaration(
                source_unit_selection_id="leader", bodyguard_unit_selection_id="source"
            ),
        )
        if attached
        else (),
        enemy_unit_specs=(("target", "core-intercessor-like-infantry", "core-intercessor-like", 2),)
        + (("enemy-leader", "core-character-leader", "core-character-leader", 1),) * attached,
        enemy_attachment_declarations=(
            AttachmentDeclaration(
                source_unit_selection_id="enemy-leader", bodyguard_unit_selection_id="target"
            ),
        )
        if attached
        else (),
        catalog=catalog,
        game_id="order41-explosives",
    )
    state = lifecycle.state
    assert state is not None
    for key, x in (("source", 10), ("target", target_x)):
        _replace_unit_poses(
            state,
            unit_instance_id=units[key].unit_instance_id,
            poses=(Pose.at(x, 10), Pose.at(x, 12)),
        )
    if attached:
        for key, x in (("leader", 10), ("enemy-leader", target_x)):
            _replace_unit_poses(
                state, unit_instance_id=units[key].unit_instance_id, poses=(Pose.at(x, 14),)
            )
    if extra_friendly:
        _replace_unit_poses(
            state, unit_instance_id=units["other"].unit_instance_id, poses=(Pose.at(10, 22),)
        )
    state.gain_command_points(
        player_id="player-a",
        amount=2,
        source_id="order41:fixture-cp",
        source_kind=CommandPointSourceKind.COMMAND_PHASE_START,
    )
    return GameLifecycle.from_payload(lifecycle.to_payload()), units
