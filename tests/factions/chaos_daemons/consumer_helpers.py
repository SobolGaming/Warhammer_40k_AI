"""Real Bloodcrushers loaded by lifecycle; bounded component battle checkpoints."""

import json
from dataclasses import replace
from pathlib import Path
from typing import cast

import pytest

from tests.support.faction_batch01 import (
    CRUSHERS,
    LORD,
    anchor,
    casualty_checkpoint,
    events,
    locate,
    request,
    scene,
    selection,
)
from tests.support.section02_fixtures import Section02Definitions
from tests.support.section11_fixtures import (
    begin,
    choose,
    propose,
    roll,
    targets,
    witness,
)
from warhammer40k_core.adapters.local_session import LocalGameSession
from warhammer40k_core.engine.decision_result import DecisionResult
from warhammer40k_core.engine.event_log import JsonValue
from warhammer40k_core.engine.phase import BattlePhase, LifecycleStatusKind
from warhammer40k_core.engine.replay import ReplayRunner
from warhammer40k_core.geometry.pose import Pose

__all__ = [
    "CRUSHERS",
    "LORD",
    "BattlePhase",
    "DecisionResult",
    "JsonValue",
    "LifecycleStatusKind",
    "LocalGameSession",
    "Path",
    "Pose",
    "ReplayRunner",
    "Section02Definitions",
    "anchor",
    "begin",
    "cast",
    "casualty_checkpoint",
    "choose",
    "events",
    "json",
    "locate",
    "propose",
    "pytest",
    "replace",
    "request",
    "roll",
    "scene",
    "selection",
    "targets",
    "witness",
]
