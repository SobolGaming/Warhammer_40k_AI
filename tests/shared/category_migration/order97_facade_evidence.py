"""Clause assertions for Heavy's accepted movement and Category 07 phase order."""

from __future__ import annotations

import json
from math import isclose, sqrt
from typing import cast

import pytest

from tests.core_clause_evidence_helpers import assert_persistence_viewers_replay, clause_session
from tests.d09_heavy_helpers import (
    assert_heavy_checkpoint,
    complete_heavy_attack,
    heavy_session,
    move_heavy_unit,
    reach_second_player_movement,
)
from tests.phase13b_shooting_declaration_helpers import _proposal_from_request
from tests.psychic_modifier_helpers import pending_request, submit_fixture_request
from tests.sequential_translation_helpers import leading_first_translation_paths
from warhammer40k_core.adapters.local_session import LocalGameSession
from warhammer40k_core.engine.event_log import JsonValue, validate_json_value
from warhammer40k_core.engine.movement_proposals import (
    MovementProposalPayload,
    MovementProposalRequest,
)
from warhammer40k_core.engine.phase import BattlePhase, LifecycleStatusKind
from warhammer40k_core.engine.weapon_abilities import HEAVY_RULE_ID
from warhammer40k_core.geometry.pathing import PathWitness
from warhammer40k_core.geometry.pose import Pose

__all__: list[str] = []
__all__ += ["HEAVY_RULE_ID", "BattlePhase", "JsonValue", "LifecycleStatusKind"]
__all__ += ["LocalGameSession", "MovementProposalPayload", "MovementProposalRequest"]
__all__ += ["PathWitness", "Pose", "_proposal_from_request", "assert_heavy_checkpoint"]
__all__ += ["assert_persistence_viewers_replay", "cast", "clause_session"]
__all__ += ["complete_heavy_attack", "heavy_session", "isclose", "json"]
__all__ += ["leading_first_translation_paths", "move_heavy_unit", "pending_request", "pytest"]
__all__ += ["reach_second_player_movement", "sqrt", "submit_fixture_request"]
__all__ += ["validate_json_value"]
