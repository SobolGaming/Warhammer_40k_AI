from __future__ import annotations

from dataclasses import replace

import pytest

from tests.phase10p_reserves_helpers import (
    battle_state_with_reserve,
    single_model_reserve_placement,
)
from tests.unit_keyword_helpers import with_unit_keywords
from warhammer40k_core.core.ruleset_descriptor import MovementMode
from warhammer40k_core.engine.battlefield_state import BattlefieldPlacementKind, BattlefieldScenario
from warhammer40k_core.engine.charge_eligibility import charge_unit_ineligibility_reason
from warhammer40k_core.engine.charge_phase_state import ChargePhaseState
from warhammer40k_core.engine.large_model_restrictions import large_model_activity_reason
from warhammer40k_core.engine.phase import BattlePhase, GameLifecycleError
from warhammer40k_core.engine.phases.movement_resolvers import resolve_normal_move
from warhammer40k_core.engine.reaction_windows import ReactionWindow, ReactionWindowKind
from warhammer40k_core.engine.reserves import (
    BattlefieldEdge,
    LargeModelReservePlacementException,
    apply_reinforcement_placement_to_battlefield,
    resolve_reserve_arrival,
)
from warhammer40k_core.engine.rules_units import rules_unit_view_by_id
from warhammer40k_core.engine.shooting_eligibility_state import shooting_state_restriction_reason
from warhammer40k_core.engine.triggered_movement import (
    TriggeredMovementDescriptor,
    TriggeredMovementHandler,
    TriggeredMovementKind,
)
from warhammer40k_core.geometry.pathing import PathWitness
from warhammer40k_core.geometry.pose import Pose

__all__: list[str] = []
__all__ += ["BattlePhase", "BattlefieldEdge", "BattlefieldPlacementKind", "BattlefieldScenario"]
__all__ += ["ChargePhaseState", "GameLifecycleError", "LargeModelReservePlacementException"]
__all__ += ["MovementMode", "PathWitness", "Pose", "ReactionWindow", "ReactionWindowKind"]
__all__ += ["TriggeredMovementDescriptor", "TriggeredMovementHandler", "TriggeredMovementKind"]
__all__ += ["apply_reinforcement_placement_to_battlefield", "battle_state_with_reserve"]
__all__ += ["charge_unit_ineligibility_reason", "large_model_activity_reason", "pytest"]
__all__ += ["replace", "resolve_normal_move", "resolve_reserve_arrival", "rules_unit_view_by_id"]
__all__ += ["shooting_state_restriction_reason", "single_model_reserve_placement"]
__all__ += ["with_unit_keywords"]
