"""Canonical catalog-backed fixtures for absent and numeric-zero Movement."""

from dataclasses import replace

from tests.phase15a_charge_test_support import _charge_lifecycle, _compact_test_unit_poses
from tests.sequential_translation_helpers import leading_first_translation_paths
from warhammer40k_core.adapters.local_session import LocalGameSession
from warhammer40k_core.core.army_catalog import ArmyCatalog
from warhammer40k_core.core.attributes import Characteristic, CharacteristicValue
from warhammer40k_core.engine.phase import BattlePhase
from warhammer40k_core.geometry.pathing import PathWitness
from warhammer40k_core.geometry.pose import Pose


def movement_catalog(
    movement: CharacteristicValue, *, datasheet_id: str = "core-intercessor-like-infantry"
) -> ArmyCatalog:
    catalog = ArmyCatalog.phase9a_canonical_content_pack()
    return replace(
        catalog,
        datasheets=tuple(
            replace(
                sheet,
                model_profiles=tuple(
                    replace(
                        profile,
                        characteristics=tuple(
                            movement if value.characteristic is Characteristic.MOVEMENT else value
                            for value in profile.characteristics
                        ),
                    )
                    for profile in sheet.model_profiles
                ),
            )
            if sheet.datasheet_id == datasheet_id
            else sheet
            for sheet in catalog.datasheets
        ),
    )


def movement_session(movement: CharacteristicValue) -> LocalGameSession:
    lifecycle, _ = _charge_lifecycle(
        alpha_unit_ids=("mover",),
        enemy_model_poses=_compact_test_unit_poses(origin=Pose.at(30, 20), model_count=5),
        game_id="order115-movement",
        catalog=movement_catalog(movement),
    )
    state = lifecycle.state
    assert state is not None
    state.battle_phase_index = state.battle_phase_sequence.index(BattlePhase.MOVEMENT)
    return LocalGameSession(lifecycle)


def movement_witness(session: LocalGameSession, *, kind: str) -> PathWitness:
    state = session.lifecycle.state
    assert state is not None
    assert state.battlefield_state is not None
    placement = state.battlefield_state.unit_placement_by_id("army-alpha:mover")
    paths: list[tuple[str, tuple[Pose, ...]]] = []
    for row in placement.model_placements:
        start = row.pose
        end = Pose.at(start.position.x + 1, start.position.y)
        poses = {
            "translate": (start, end),
            "return": (start, end, start),
            "rotate": (
                start,
                Pose.at(start.position.x, start.position.y, facing_degrees=90),
            ),
            "hold": (start, start),
        }[kind]
        paths.append((row.model_instance_id, poses))
    return PathWitness.for_paths(
        leading_first_translation_paths(tuple(paths), dx=1.0 if kind == "translate" else 0.0)
    )
