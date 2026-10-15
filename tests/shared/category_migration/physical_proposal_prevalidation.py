"""C03-04: prevalidation must preserve replayable authority and typed diagnostics."""

from __future__ import annotations

import copy
import json

import pytest

from tests.physical_proposal_prevalidation_helpers import FAMILIES, proposal_session
from warhammer40k_core.adapters.event_stream import EventStreamCursor
from warhammer40k_core.adapters.local_session import LocalGameSession
from warhammer40k_core.adapters.network import submit_network_parameterized_payload
from warhammer40k_core.engine.event_log import JsonValue
from warhammer40k_core.engine.phase import LifecycleStatusKind
from warhammer40k_core.engine.replay import ReplayRunner, ReplayRunStatus

__all__: list[str] = []
__all__ += ["FAMILIES", "EventStreamCursor", "JsonValue", "LifecycleStatusKind"]
__all__ += ["LocalGameSession", "ReplayRunStatus", "ReplayRunner", "copy", "json"]
__all__ += ["proposal_session", "pytest", "submit_network_parameterized_payload"]
