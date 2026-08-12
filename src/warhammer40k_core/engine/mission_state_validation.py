from __future__ import annotations

from dataclasses import replace

from warhammer40k_core.core.ruleset_descriptor import RulesetDescriptor
from warhammer40k_core.engine.battlefield_state import BattlefieldRuntimeState
from warhammer40k_core.engine.mission_setup import MissionSetup
from warhammer40k_core.engine.missions import (
    canonical_layoutless_mission_setup_from_source,
    validate_mission_setup_source_layout,
)
from warhammer40k_core.engine.objective_control_sources import (
    source_linked_terrain_objectives_supported,
)
from warhammer40k_core.engine.phase import GameLifecycleError
from warhammer40k_core.rules.source_packages.warhammer_40000_11th import (
    chapter_approved_2026_27 as eleventh_ca_2026_27_source,
)
from warhammer40k_core.rules.source_packages.warhammer_40000_11th import (
    event_companion_2026_06 as event_companion_source,
)


def validate_game_config_mission_setup(
    mission_setup: MissionSetup | None,
    *,
    ruleset_descriptor: RulesetDescriptor,
) -> None:
    if mission_setup is None:
        return
    validate_mission_setup_source_layout(mission_setup)
    if mission_setup.objective_terrain_areas and not source_linked_terrain_objectives_supported(
        ruleset_descriptor
    ):
        raise GameLifecycleError(
            "GameConfig ruleset descriptor does not support source-linked terrain objectives."
        )


def validate_game_state_mission_setup(
    mission_setup: MissionSetup | None,
    *,
    battlefield_state: BattlefieldRuntimeState | None,
) -> None:
    if mission_setup is not None:
        validate_mission_setup_source_layout(mission_setup)
    validate_battlefield_state_matches_mission_setup(
        battlefield_state=battlefield_state,
        mission_setup=mission_setup,
    )


def validate_battlefield_state_matches_mission_setup(
    *,
    battlefield_state: BattlefieldRuntimeState | None,
    mission_setup: MissionSetup | None,
) -> None:
    if battlefield_state is None or mission_setup is None:
        return
    if (
        battlefield_state.battlefield_width_inches != mission_setup.battlefield_width_inches
        or battlefield_state.battlefield_depth_inches != mission_setup.battlefield_depth_inches
    ):
        raise GameLifecycleError(
            "GameState battlefield runtime geometry drifted from MissionSetup."
        )
    has_source_geometry = (
        mission_setup.battlefield_layout_id is not None
        or canonical_layoutless_mission_setup_from_source(mission_setup) is not None
    )
    if not has_source_geometry:
        return
    if battlefield_state.terrain_features != mission_setup.terrain_features:
        raise GameLifecycleError(
            "GameState battlefield runtime geometry drifted from source MissionSetup."
        )


def validate_recorded_mission_setup(
    mission_setup: MissionSetup,
    *,
    battlefield_state: BattlefieldRuntimeState | None,
) -> None:
    validate_mission_setup_source_layout(mission_setup)
    if mission_setup.objective_terrain_areas:
        raise GameLifecycleError(
            "Source-linked terrain objectives must be configured before GameState creation."
        )
    validate_battlefield_state_matches_mission_setup(
        battlefield_state=battlefield_state,
        mission_setup=mission_setup,
    )


def runtime_ruleset_descriptor_for_mission_setup(
    mission_setup: MissionSetup | None,
    *,
    rules_overlay_ids: tuple[str, ...],
) -> RulesetDescriptor:
    if mission_setup is not None and (
        mission_setup.mission_pack_id
        in {
            eleventh_ca_2026_27_source.MISSION_PACK_ID,
            event_companion_source.MISSION_PACK_ID,
        }
    ):
        descriptor = RulesetDescriptor.warhammer_40000_eleventh_chapter_approved_2026_27()
    else:
        descriptor = RulesetDescriptor.warhammer_40000_eleventh()
    return replace(descriptor, rules_overlay_ids=rules_overlay_ids, descriptor_hash="")
