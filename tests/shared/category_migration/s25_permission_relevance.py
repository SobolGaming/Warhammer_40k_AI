"""Normal pre-start permission relevance and exact selected grant-source regressions."""

import json
from collections import Counter
from dataclasses import replace
from typing import TYPE_CHECKING, cast

import pytest

from tests.order128_helpers import assert_checkpoint
from tests.phase13b_shooting_declaration_helpers import proposal_from_request
from tests.psychic_modifier_helpers import submit_fixture_request
from tests.s25_native_profile_helpers import native_profile_request
from tests.s25_permission_relevance_helpers import declared_activated_relevance_ability
from tests.s25_shared_unit_permission_helpers import SHARED_PERMISSION_SOURCE
from warhammer40k_core.core.attributes import Characteristic
from warhammer40k_core.engine.attack_gathering_dependencies import (
    validate_save_gathering_characteristics,
)
from warhammer40k_core.engine.catalog_modifier_ignore import (
    ModifierIgnoreKind,
    modifier_ignore_permissions_for_subject,
    modifier_ignore_sources_for_gathering,
)
from warhammer40k_core.engine.decision_request import DecisionError
from warhammer40k_core.engine.event_log import JsonValue, validate_json_value
from warhammer40k_core.engine.modifier_permission_context import ModifierPermissionAttackContext
from warhammer40k_core.engine.phase import GameLifecycleError, LifecycleStatusKind
from warhammer40k_core.engine.weapon_declaration import WeaponDeclarationPayload
from warhammer40k_core.engine.weapon_selection_context import (
    WeaponSelectionContext,
    WeaponSelectionContextPayload,
)

if TYPE_CHECKING:
    from warhammer40k_core.engine.catalog_modifier_ignore_sources import (
        ModifierIgnoreSourceTemplate,
    )


__all__: list[str] = []
__all__ += ["Characteristic", "Counter", "DecisionError", "GameLifecycleError", "JsonValue"]
__all__ += ["LifecycleStatusKind", "ModifierIgnoreKind", "ModifierIgnoreSourceTemplate"]
__all__ += ["SHARED_PERMISSION_SOURCE", "TYPE_CHECKING", "ModifierPermissionAttackContext"]
__all__ += ["WeaponDeclarationPayload", "WeaponSelectionContext", "WeaponSelectionContextPayload"]
__all__ += ["assert_checkpoint", "cast", "declared_activated_relevance_ability", "json"]
__all__ += ["modifier_ignore_permissions_for_subject", "modifier_ignore_sources_for_gathering"]
__all__ += ["native_profile_request", "proposal_from_request", "pytest", "replace"]
__all__ += ["submit_fixture_request", "validate_json_value"]
__all__ += ["validate_save_gathering_characteristics"]
