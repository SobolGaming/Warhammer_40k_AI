from __future__ import annotations

from typing import TypedDict


class MissionPackScoringDefinitionPayload(TypedDict):
    game_length_battle_rounds: int
    primary_scoring_phase: str
    primary_scoring_timing: str
    secondary_vp_per_score: int
    mission_action_vp: int
    primary_vp_cap: int
    secondary_vp_cap: int
    total_vp_cap: int
    secondary_max_vp_per_turn: int
    secondary_vp_cap_scope: str
    end_of_round_scoring_windows: list[str]
    end_of_game_scoring_windows: list[str]
    reserve_destruction_timing: str
    reserve_destruction_battle_round: int | None
    reserve_destruction_excludes_during_battle_strategic_reserves: bool
    reserve_destruction_only_declare_battle_formations: bool
    source_id: str
