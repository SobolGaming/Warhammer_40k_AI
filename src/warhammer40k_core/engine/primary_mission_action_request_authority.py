from __future__ import annotations

import json
from typing import TYPE_CHECKING, cast

from warhammer40k_core.engine.event_log import JsonValue
from warhammer40k_core.engine.phase import BattlePhase, GameLifecycleError
from warhammer40k_core.engine.primary_mission_action_lifecycle_evidence import (
    MissionActionStartAuthorityEvidence,
    PrimaryMissionActionStartEvidence,
)
from warhammer40k_core.engine.runtime_modifiers import RuntimeModifierRegistry

if TYPE_CHECKING:
    from warhammer40k_core.engine.game_state import GameState
    from warhammer40k_core.engine.mission_action_options import MissionActionStartOption


_DECLINE_MISSION_ACTION_START_OPTION_ID = "continue_to_shooting"


def validate_recomputed_primary_mission_action_request_authority(
    *,
    state: GameState,
    evidence: PrimaryMissionActionStartEvidence,
) -> None:
    """Require the stored request and every option to match the start boundary."""

    _validate_recomputed_request_authority(
        state=state,
        player_id=evidence.player_id,
        battle_round=evidence.battle_round,
        authority=evidence.start_authority,
        selected_mission_action_id=evidence.mission_action_id,
        runtime_modifier_registry=None,
    )


def validate_recomputed_primary_mission_action_opportunity_authority(
    *,
    state: GameState,
    player_id: str,
    battle_round: int,
    authority: MissionActionStartAuthorityEvidence,
    runtime_modifier_registry: RuntimeModifierRegistry | None = None,
) -> None:
    if authority.request_kind != "opportunity":
        raise GameLifecycleError(
            "Primary Mission Action opportunity authority request kind drifted."
        )
    _validate_recomputed_request_authority(
        state=state,
        player_id=player_id,
        battle_round=battle_round,
        authority=authority,
        selected_mission_action_id=None,
        runtime_modifier_registry=runtime_modifier_registry,
    )


def validate_recomputed_primary_mission_action_direct_authority(
    *,
    state: GameState,
    player_id: str,
    battle_round: int,
    mission_action_id: str,
    authority: MissionActionStartAuthorityEvidence,
    runtime_modifier_registry: RuntimeModifierRegistry | None = None,
) -> None:
    """Recompute one direct Action request without recording another request."""

    if authority.request_kind != "direct":
        raise GameLifecycleError("Primary Mission Action direct authority request kind drifted.")
    _validate_recomputed_request_authority(
        state=state,
        player_id=player_id,
        battle_round=battle_round,
        authority=authority,
        selected_mission_action_id=mission_action_id,
        runtime_modifier_registry=runtime_modifier_registry,
    )


def _validate_recomputed_request_authority(
    *,
    state: GameState,
    player_id: str,
    battle_round: int,
    authority: MissionActionStartAuthorityEvidence,
    selected_mission_action_id: str | None,
    runtime_modifier_registry: RuntimeModifierRegistry | None,
) -> None:

    from warhammer40k_core.engine.mission_action_options import (
        mission_action_for_state,
        mission_action_opportunity_options,
        mission_action_start_options,
    )

    phase = BattlePhase.SHOOTING
    registry = (
        RuntimeModifierRegistry.empty()
        if runtime_modifier_registry is None
        else runtime_modifier_registry
    )
    if type(registry) is not RuntimeModifierRegistry:
        raise GameLifecycleError("Primary Mission Action request authority requires modifiers.")
    if authority.request_kind == "opportunity":
        options = mission_action_opportunity_options(
            state=state,
            player_id=player_id,
            runtime_modifier_registry=registry,
        )
        action_option_ids = [option.option_id() for option in options]
        expected_request: dict[str, object] = {
            "game_id": state.game_id,
            "player_id": player_id,
            "battle_round": battle_round,
            "phase": phase.value,
            "mission_action_opportunity": True,
            "legal_mission_action_ids": cast(
                list[JsonValue],
                sorted({option.action.mission_action_id for option in options}),
            ),
            "legal_action_option_ids": cast(list[JsonValue], action_option_ids),
            "legal_option_ids": cast(
                list[JsonValue],
                sorted((*action_option_ids, _DECLINE_MISSION_ACTION_START_OPTION_ID)),
            ),
        }
        expected_options = (
            *(
                _option_authority_row(
                    option=option,
                    state=state,
                    player_id=player_id,
                    phase=phase,
                    opportunity_action_option_ids=action_option_ids,
                )
                for option in options
            ),
            (
                _DECLINE_MISSION_ACTION_START_OPTION_ID,
                "Continue to shooting",
                _canonical_json(
                    {
                        "game_id": state.game_id,
                        "player_id": player_id,
                        "battle_round": battle_round,
                        "phase": phase.value,
                        "mission_action_opportunity": True,
                        "legal_action_option_ids": action_option_ids,
                    }
                ),
            ),
        )
    elif authority.request_kind == "direct":
        if selected_mission_action_id is None:
            raise GameLifecycleError(
                "Primary Mission Action direct authority lacks selected Action identity."
            )
        action = mission_action_for_state(
            state=state,
            mission_action_id=selected_mission_action_id,
        )
        options = mission_action_start_options(
            state=state,
            player_id=player_id,
            action=action,
            runtime_modifier_registry=registry,
        )
        action_option_ids = [option.option_id() for option in options]
        expected_request = {
            "game_id": state.game_id,
            "player_id": player_id,
            "battle_round": battle_round,
            "phase": phase.value,
            "mission_action_id": selected_mission_action_id,
            "legal_option_ids": cast(list[JsonValue], action_option_ids),
        }
        expected_options = tuple(
            _option_authority_row(
                option=option,
                state=state,
                player_id=player_id,
                phase=phase,
                opportunity_action_option_ids=None,
            )
            for option in options
        )
    else:
        raise GameLifecycleError(
            "Primary Mission Action complete start authority inventory drifted."
        )

    actual_options = tuple(
        sorted(
            (option.option_id, option.label, option.payload_json) for option in authority.options
        )
    )
    if authority.request_payload_json != _canonical_json(
        expected_request
    ) or actual_options != tuple(sorted(expected_options)):
        raise GameLifecycleError(
            "Primary Mission Action complete start authority inventory drifted."
        )


def _option_authority_row(
    *,
    option: MissionActionStartOption,
    state: GameState,
    player_id: str,
    phase: BattlePhase,
    opportunity_action_option_ids: list[str] | None,
) -> tuple[str, str, str]:
    payload: dict[str, object] = dict(option.payload(state=state, player_id=player_id, phase=phase))
    if opportunity_action_option_ids is not None:
        payload = {
            **payload,
            "mission_action_opportunity": True,
            "legal_action_option_ids": cast(list[JsonValue], opportunity_action_option_ids),
        }
    return option.option_id(), option.label(state=state), _canonical_json(payload)


def _canonical_json(value: object) -> str:
    return json.dumps(value, sort_keys=True, separators=(",", ":"), ensure_ascii=True)


__all__ = (
    "validate_recomputed_primary_mission_action_direct_authority",
    "validate_recomputed_primary_mission_action_opportunity_authority",
    "validate_recomputed_primary_mission_action_request_authority",
)
