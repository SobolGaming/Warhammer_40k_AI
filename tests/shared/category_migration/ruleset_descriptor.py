from __future__ import annotations

import json
from dataclasses import replace
from datetime import date

import pytest

from warhammer40k_core.core.objectives import ObjectiveAnchorKind
from warhammer40k_core.core.ruleset import RulesetError, RulesetId
from warhammer40k_core.core.ruleset_descriptor import (
    BattlePhaseKind,
    CoherencyPolicyDescriptor,
    CoherencyPolicyKind,
    MovementMode,
    MovementModePolicy,
    MovementPolicyDescriptor,
    ObjectivePolicyDescriptor,
    RulesetDescriptor,
    RulesetDescriptorError,
    SetupStepKind,
    TerrainEndpointSupportPolicy,
    TerrainFeatureKind,
    TerrainFeatureMovementPolicy,
    TerrainMovementPolicy,
    TerrainObjectiveControlPolicy,
    TerrainTraversalMode,
)
from warhammer40k_core.rules.source_packages.warhammer_40000_11th import tacoma_open_2026


def _terrain_feature_policies() -> tuple[TerrainFeatureMovementPolicy, ...]:
    return RulesetDescriptor.warhammer_40000_eleventh().terrain_movement_policy.feature_policies


__all__: list[str] = []
__all__ += ["BattlePhaseKind", "CoherencyPolicyDescriptor", "CoherencyPolicyKind", "MovementMode"]
__all__ += ["MovementModePolicy", "MovementPolicyDescriptor", "ObjectiveAnchorKind"]
__all__ += ["ObjectivePolicyDescriptor", "RulesetDescriptor", "RulesetDescriptorError"]
__all__ += ["RulesetError", "RulesetId", "SetupStepKind", "TerrainEndpointSupportPolicy"]
__all__ += ["TerrainFeatureKind", "TerrainFeatureMovementPolicy", "TerrainMovementPolicy"]
__all__ += ["TerrainObjectiveControlPolicy", "TerrainTraversalMode", "_terrain_feature_policies"]
__all__ += ["date", "json", "pytest", "replace", "tacoma_open_2026"]
