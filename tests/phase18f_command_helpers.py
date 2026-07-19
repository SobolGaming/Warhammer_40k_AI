from __future__ import annotations

from dataclasses import dataclass

from warhammer40k_core.adapters.local_session import LocalGameSession
from warhammer40k_core.engine.phase import LifecycleStatus


@dataclass(slots=True)
class PreRecordUnsupportedSession(LocalGameSession):
    def submit_option(self, *, request_id: str, option_id: str, result_id: str) -> LifecycleStatus:
        state = self.lifecycle.state
        assert state is not None
        return LifecycleStatus.unsupported(
            stage=state.stage,
            message="Test rule path is unsupported before decision recording.",
        )


@dataclass(slots=True)
class RecordedUnsupportedSession(LocalGameSession):
    def submit_option(self, *, request_id: str, option_id: str, result_id: str) -> LifecycleStatus:
        super().submit_option(request_id=request_id, option_id=option_id, result_id=result_id)
        state = self.lifecycle.state
        assert state is not None
        return LifecycleStatus.unsupported(
            stage=state.stage,
            message="Test rule path is unsupported after decision recording.",
        )


def pre_record_unsupported_session() -> LocalGameSession:
    return PreRecordUnsupportedSession()


def recorded_unsupported_session() -> LocalGameSession:
    return RecordedUnsupportedSession()
