"""Real melee activation and the original strict generic weapon-dispatch guards."""

from typing import cast

import pytest

from tests.epic_challenge_helpers import epic_checkpoint
from tests.psychic_modifier_helpers import submit_fixture_request
from tests.s25_characteristic_melee_projection_helpers import projection_melee_request
from warhammer40k_core.core.army_catalog import ArmyCatalog
from warhammer40k_core.core.attributes import Characteristic, CharacteristicValue
from warhammer40k_core.engine.decision_request import DecisionError
from warhammer40k_core.engine.event_log import JsonValue
from warhammer40k_core.engine.fight_resolution import MeleeDeclarationProposalRequest
from warhammer40k_core.engine.phase import GameLifecycleError, LifecycleStatusKind
from warhammer40k_core.engine.rule_ir_weapon_modifiers import rule_ir_modified_weapon_profile

__all__: list[str] = []
__all__ += ["ArmyCatalog", "Characteristic", "CharacteristicValue", "DecisionError"]
__all__ += ["GameLifecycleError", "JsonValue", "LifecycleStatusKind"]
__all__ += ["MeleeDeclarationProposalRequest", "cast", "epic_checkpoint"]
__all__ += ["projection_melee_request", "pytest", "rule_ir_modified_weapon_profile"]
__all__ += ["submit_fixture_request"]
