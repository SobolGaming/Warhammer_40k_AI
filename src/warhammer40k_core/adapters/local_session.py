from __future__ import annotations

import copy
import hashlib
from dataclasses import dataclass, field
from typing import Self, TypedDict, cast

from warhammer40k_core.adapters.access_control import ViewerContext
from warhammer40k_core.adapters.contracts import (
    AdapterGameSession,
    AdapterSessionHistoryPayload,
    AdapterSessionIdentityPayload,
)
from warhammer40k_core.adapters.decisions import submit_option, submit_parameterized_payload
from warhammer40k_core.adapters.event_stream import (
    EventStreamCursor,
    EventStreamDeltaPayload,
    EventStreamPagePayload,
)
from warhammer40k_core.adapters.projection import (
    GameViewPayload,
    RulesCatalogViewPayload,
    project_game_view,
    project_rules_catalog_view,
)
from warhammer40k_core.adapters.replay import submit_replay_record
from warhammer40k_core.adapters.support_profile import SupportProfilePayload, build_support_profile
from warhammer40k_core.core.rng import RandomSource, RandomSourceError, RandomSourcePayload
from warhammer40k_core.engine.decision import DiceRollManager
from warhammer40k_core.engine.decision_record import DecisionRecord
from warhammer40k_core.engine.decision_request import DecisionError
from warhammer40k_core.engine.event_log import (
    EventLogError,
    JsonValue,
    canonical_json,
    validate_json_value,
)
from warhammer40k_core.engine.game_state import GameConfig
from warhammer40k_core.engine.lifecycle import GameLifecycle, GameLifecyclePayload
from warhammer40k_core.engine.phase import GameLifecycleError, LifecycleStatus, LifecycleStatusKind
from warhammer40k_core.engine.replay import (
    ReplayArtifact,
    ReplayArtifactError,
    ReplayArtifactPayload,
    ReplaySourceIdentity,
    ReplaySourceIdentityPayload,
    replay_event_log_hash,
)

LOCAL_GAME_SESSION_PERSISTENCE_SCHEMA_VERSION = "local-game-session-persistence-v1"


class LocalGameSessionPersistencePayload(TypedDict):
    schema_version: str
    lifecycle: GameLifecyclePayload
    initial_replay_lifecycle: GameLifecyclePayload | None
    source_identity: ReplaySourceIdentityPayload
    rng_state: RandomSourcePayload
    replay_artifact: ReplayArtifactPayload
    lifecycle_hash: str
    decision_records_hash: str
    event_log_hash: str
    rng_state_hash: str
    content_hash: str


class LocalGameSessionPersistenceError(GameLifecycleError):
    """Raised when a LocalGameSession persistence checkpoint is invalid or drifted."""


def _new_parameterized_lifecycle() -> GameLifecycle:
    return GameLifecycle(parameterized_movement_proposals=True)


@dataclass(slots=True)
class LocalGameSession(AdapterGameSession):
    lifecycle: GameLifecycle = field(default_factory=_new_parameterized_lifecycle)
    _initial_replay_lifecycle_payload: GameLifecyclePayload | None = field(
        default=None,
        init=False,
        repr=False,
    )
    _persistence_payload_cache: JsonValue = field(
        default=None,
        init=False,
        repr=False,
    )

    def fork(self) -> Self:
        clone = type(self)(
            lifecycle=GameLifecycle.from_payload(copy.deepcopy(self.lifecycle.to_payload()))
        )
        clone._initial_replay_lifecycle_payload = copy.deepcopy(
            self._initial_replay_lifecycle_payload
        )
        clone._persistence_payload_cache = copy.deepcopy(self._persistence_payload_cache)
        return clone

    def to_persistence_payload(self) -> JsonValue:
        lifecycle_payload = _lifecycle_payload_copy(self.lifecycle)
        lifecycle_hash = _payload_sha256(cast(JsonValue, lifecycle_payload))
        initial_replay_payload = copy.deepcopy(self._initial_replay_lifecycle_payload)
        cached = self._persistence_payload_cache
        if (
            isinstance(cached, dict)
            and cached.get("lifecycle_hash") == lifecycle_hash
            and _payloads_match_exactly(
                cached.get("initial_replay_lifecycle"),
                cast(JsonValue, initial_replay_payload),
            )
        ):
            return copy.deepcopy(cached)
        effective_initial_payload = (
            lifecycle_payload
            if initial_replay_payload is None
            else copy.deepcopy(initial_replay_payload)
        )
        if initial_replay_payload is None and self.lifecycle.decision_controller.records:
            raise LocalGameSessionPersistenceError(
                "LocalGameSession persistence requires its initial replay snapshot."
            )
        try:
            source_identity = ReplaySourceIdentity.from_lifecycle(self.lifecycle)
            rng_state = _current_rng_state(self.lifecycle)
            replay_artifact = ReplayArtifact.capture(
                artifact_id=f"session-persistence:{self.lifecycle.config.game_id}",
                initial_lifecycle_payload=effective_initial_payload,
                final_lifecycle=self.lifecycle,
            )
        except ReplayArtifactError as exc:
            raise LocalGameSessionPersistenceError(
                "LocalGameSession persistence replay capture failed."
            ) from exc
        payload_without_hash: dict[str, JsonValue] = {
            "schema_version": LOCAL_GAME_SESSION_PERSISTENCE_SCHEMA_VERSION,
            "lifecycle": cast(JsonValue, lifecycle_payload),
            "initial_replay_lifecycle": cast(JsonValue, initial_replay_payload),
            "source_identity": cast(JsonValue, source_identity.to_payload()),
            "rng_state": cast(JsonValue, rng_state),
            "replay_artifact": cast(JsonValue, replay_artifact.to_payload()),
            "lifecycle_hash": lifecycle_hash,
            "decision_records_hash": _decision_records_hash(self.lifecycle),
            "event_log_hash": replay_event_log_hash(self.lifecycle),
            "rng_state_hash": _payload_sha256(cast(JsonValue, rng_state)),
        }
        payload: dict[str, JsonValue] = {
            **payload_without_hash,
            "content_hash": _payload_sha256(cast(JsonValue, payload_without_hash)),
        }
        validate_json_value(payload)
        validated = validate_json_value(payload)
        self._persistence_payload_cache = copy.deepcopy(validated)
        return copy.deepcopy(validated)

    def authoritative_identity_payload(self) -> AdapterSessionIdentityPayload:
        config = self.lifecycle.config
        catalog = self.rules_catalog_view()
        return {
            "game_id": config.game_id,
            "player_ids": list(config.player_ids),
            "ruleset_id": validate_json_value(config.ruleset_descriptor.ruleset_id.to_payload()),
            "ruleset_descriptor_hash": config.ruleset_descriptor.descriptor_hash,
            "rules_overlay_ids": list(config.ruleset_descriptor.rules_overlay_ids),
            "catalog_id": catalog["catalog_id"],
            "source_package_id": catalog["source_package_id"],
            "source_hash": catalog["source_hash"],
        }

    def authoritative_history_payload(self) -> AdapterSessionHistoryPayload:
        checkpoint = self.to_persistence_payload()
        if not isinstance(checkpoint, dict):
            raise LocalGameSessionPersistenceError(
                "LocalGameSession persistence checkpoint must be an object."
            )
        rng_state = _current_rng_state(self.lifecycle)
        return {
            "decision_records": [
                validate_json_value(cast(JsonValue, record.to_payload()))
                for record in self.lifecycle.decision_controller.records
            ],
            "event_records": [
                validate_json_value(cast(JsonValue, record.to_payload()))
                for record in self.lifecycle.decision_controller.event_log.records
            ],
            "rng_seed": rng_state["seed"],
            "rng_history": list(rng_state["history"]),
            "rng_draw_count": rng_state["draw_count"],
            "checkpoint_hash": _payload_sha256(validate_json_value(checkpoint)),
            "authoritative_state_hash": _payload_sha256(
                cast(JsonValue, self.lifecycle.to_payload())
            ),
        }

    @classmethod
    def from_persistence_payload(cls, payload: JsonValue) -> Self:
        value = _persistence_object(payload)
        expected_keys = {
            "schema_version",
            "lifecycle",
            "initial_replay_lifecycle",
            "source_identity",
            "rng_state",
            "replay_artifact",
            "lifecycle_hash",
            "decision_records_hash",
            "event_log_hash",
            "rng_state_hash",
            "content_hash",
        }
        if set(value) != expected_keys:
            raise LocalGameSessionPersistenceError(
                "LocalGameSession persistence payload fields are invalid."
            )
        if value["schema_version"] != LOCAL_GAME_SESSION_PERSISTENCE_SCHEMA_VERSION:
            raise LocalGameSessionPersistenceError(
                "LocalGameSession persistence schema version drifted."
            )
        content_hash = _persistence_sha256("content_hash", value["content_hash"])
        payload_without_hash = {key: item for key, item in value.items() if key != "content_hash"}
        if _payload_sha256(cast(JsonValue, payload_without_hash)) != content_hash:
            raise LocalGameSessionPersistenceError(
                "LocalGameSession persistence content hash does not match."
            )
        try:
            lifecycle_payload = cast(GameLifecyclePayload, value["lifecycle"])
            lifecycle = GameLifecycle.from_payload(copy.deepcopy(lifecycle_payload))
            source_identity = ReplaySourceIdentity.from_payload(
                cast(ReplaySourceIdentityPayload, value["source_identity"])
            )
            stored_rng_state = cast(RandomSourcePayload, value["rng_state"])
            validated_rng_state = RandomSource.from_payload(
                copy.deepcopy(stored_rng_state)
            ).to_payload()
            replay_artifact = ReplayArtifact.from_payload(
                cast(ReplayArtifactPayload, value["replay_artifact"])
            )
        except (
            KeyError,
            TypeError,
            GameLifecycleError,
            RandomSourceError,
            ReplayArtifactError,
        ) as exc:
            raise LocalGameSessionPersistenceError(
                "LocalGameSession persistence payload could not be reconstructed."
            ) from exc
        if not _payloads_match_exactly(
            cast(JsonValue, stored_rng_state),
            cast(JsonValue, validated_rng_state),
        ):
            raise LocalGameSessionPersistenceError(
                "LocalGameSession persistence RNG payload did not round-trip exactly."
            )
        if not _payloads_match_exactly(
            cast(JsonValue, lifecycle.to_payload()),
            cast(JsonValue, lifecycle_payload),
        ):
            raise LocalGameSessionPersistenceError(
                "LocalGameSession persistence lifecycle payload did not round-trip exactly."
            )
        try:
            current_source_identity = ReplaySourceIdentity.from_lifecycle(lifecycle)
        except ReplayArtifactError as exc:
            raise LocalGameSessionPersistenceError(
                "LocalGameSession persistence source identity could not be reconstructed."
            ) from exc
        if current_source_identity != source_identity:
            raise LocalGameSessionPersistenceError(
                "LocalGameSession persistence source identity drifted."
            )
        _require_payload_hash(
            field_name="lifecycle_hash",
            stored=value["lifecycle_hash"],
            actual=_payload_sha256(cast(JsonValue, lifecycle_payload)),
        )
        _require_payload_hash(
            field_name="decision_records_hash",
            stored=value["decision_records_hash"],
            actual=_decision_records_hash(lifecycle),
        )
        _require_payload_hash(
            field_name="event_log_hash",
            stored=value["event_log_hash"],
            actual=replay_event_log_hash(lifecycle),
        )
        actual_rng_state = _current_rng_state(lifecycle)
        if not _payloads_match_exactly(
            cast(JsonValue, actual_rng_state),
            cast(JsonValue, stored_rng_state),
        ):
            raise LocalGameSessionPersistenceError(
                "LocalGameSession persistence RNG state drifted."
            )
        _require_payload_hash(
            field_name="rng_state_hash",
            stored=value["rng_state_hash"],
            actual=_payload_sha256(cast(JsonValue, actual_rng_state)),
        )
        initial_replay_value = value["initial_replay_lifecycle"]
        if initial_replay_value is not None and not isinstance(initial_replay_value, dict):
            raise LocalGameSessionPersistenceError(
                "LocalGameSession initial replay lifecycle is invalid."
            )
        effective_initial_payload = (
            lifecycle_payload
            if initial_replay_value is None
            else cast(GameLifecyclePayload, initial_replay_value)
        )
        if not _payloads_match_exactly(
            cast(JsonValue, replay_artifact.initial_lifecycle_payload),
            cast(JsonValue, effective_initial_payload),
        ):
            raise LocalGameSessionPersistenceError(
                "LocalGameSession replay initial lifecycle drifted."
            )
        if replay_artifact.source_identity != source_identity:
            raise LocalGameSessionPersistenceError(
                "LocalGameSession replay source identity drifted."
            )
        try:
            expected_replay_artifact = ReplayArtifact.capture(
                artifact_id=f"session-persistence:{lifecycle.config.game_id}",
                initial_lifecycle_payload=effective_initial_payload,
                final_lifecycle=lifecycle,
            )
        except ReplayArtifactError as exc:
            raise LocalGameSessionPersistenceError(
                "LocalGameSession expected persistence replay could not be reconstructed."
            ) from exc
        if not _payloads_match_exactly(
            cast(JsonValue, replay_artifact.to_payload()),
            cast(JsonValue, expected_replay_artifact.to_payload()),
        ):
            raise LocalGameSessionPersistenceError(
                "LocalGameSession persistence replay artifact drifted."
            )
        _verify_persistence_replay(
            artifact=replay_artifact,
            expected_lifecycle=lifecycle,
        )
        restored = cls(lifecycle=lifecycle)
        restored._initial_replay_lifecycle_payload = (
            None
            if initial_replay_value is None
            else copy.deepcopy(cast(GameLifecyclePayload, initial_replay_value))
        )
        restored._persistence_payload_cache = copy.deepcopy(value)
        return restored

    def start(self, config: GameConfig) -> LifecycleStatus:
        if type(config) is not GameConfig:
            raise GameLifecycleError("LocalGameSession config must be a GameConfig.")
        self._persistence_payload_cache = None
        status = self.lifecycle.start(config)
        self._initial_replay_lifecycle_payload = None
        return status

    def advance_until_decision_or_terminal(self) -> LifecycleStatus:
        self._persistence_payload_cache = None
        status = self.lifecycle.advance_until_decision_or_terminal()
        self._capture_initial_replay_lifecycle_if_needed(status)
        return status

    def submit_option(self, *, request_id: str, option_id: str, result_id: str) -> LifecycleStatus:
        self._persistence_payload_cache = None
        return submit_option(
            lifecycle=self.lifecycle,
            request_id=request_id,
            option_id=option_id,
            result_id=result_id,
        )

    def submit_parameterized_payload(
        self,
        *,
        request_id: str,
        payload: JsonValue,
        result_id: str,
    ) -> LifecycleStatus:
        self._persistence_payload_cache = None
        return submit_parameterized_payload(
            lifecycle=self.lifecycle,
            request_id=request_id,
            payload=payload,
            result_id=result_id,
        )

    def view(self, *, viewer_player_id: str) -> GameViewPayload:
        return project_game_view(
            lifecycle=self.lifecycle,
            viewer_player_id=viewer_player_id,
        )

    def view_for_context(self, *, viewer: ViewerContext) -> GameViewPayload:
        if type(viewer) is not ViewerContext:
            raise GameLifecycleError("LocalGameSession view requires a ViewerContext.")
        return project_game_view(
            lifecycle=self.lifecycle,
            viewer=viewer,
        )

    def rules_catalog_view(self) -> RulesCatalogViewPayload:
        return project_rules_catalog_view(catalog=self.lifecycle.config.army_catalog)

    def events_since(
        self,
        cursor: EventStreamCursor,
        *,
        viewer_player_id: str,
    ) -> EventStreamDeltaPayload:
        if type(cursor) is not EventStreamCursor:
            raise GameLifecycleError("LocalGameSession events_since requires EventStreamCursor.")
        viewer = _validate_viewer_player_id(
            lifecycle=self.lifecycle,
            viewer_player_id=viewer_player_id,
        )
        return cursor.events_since(
            self.lifecycle.decision_controller.event_log,
            viewer_player_id=viewer,
        )

    def events_since_for_context(
        self,
        cursor: EventStreamCursor,
        *,
        viewer: ViewerContext,
    ) -> EventStreamDeltaPayload:
        if type(cursor) is not EventStreamCursor:
            raise GameLifecycleError("LocalGameSession events require EventStreamCursor.")
        if type(viewer) is not ViewerContext:
            raise GameLifecycleError("LocalGameSession events require ViewerContext.")
        state = self.lifecycle.state
        if state is None:
            raise GameLifecycleError("LocalGameSession event stream requires a started lifecycle.")
        if viewer.viewer_player_id is not None and viewer.viewer_player_id not in state.player_ids:
            raise GameLifecycleError("Viewer context player is not part of this game.")
        return cursor.events_since_for_context(
            self.lifecycle.decision_controller.event_log,
            viewer=viewer,
        )

    def event_page_for_context(
        self,
        cursor: EventStreamCursor,
        *,
        viewer: ViewerContext,
        visible_limit: int,
    ) -> EventStreamPagePayload:
        self._validate_event_context(cursor=cursor, viewer=viewer)
        return cursor.page_for_context(
            self.lifecycle.decision_controller.event_log,
            viewer=viewer,
            visible_limit=visible_limit,
        )

    def visible_event_count_for_context(
        self,
        cursor: EventStreamCursor,
        *,
        viewer: ViewerContext,
    ) -> int:
        self._validate_event_context(cursor=cursor, viewer=viewer)
        return cursor.visible_count_for_context(
            self.lifecycle.decision_controller.event_log,
            viewer=viewer,
        )

    def event_record_count(self) -> int:
        return len(self.lifecycle.decision_controller.event_log.records)

    def decision_record_count(self) -> int:
        return len(self.lifecycle.decision_controller.records)

    def _validate_event_context(
        self,
        *,
        cursor: EventStreamCursor,
        viewer: ViewerContext,
    ) -> None:
        if type(cursor) is not EventStreamCursor:
            raise GameLifecycleError("LocalGameSession events require EventStreamCursor.")
        if type(viewer) is not ViewerContext:
            raise GameLifecycleError("LocalGameSession events require ViewerContext.")
        state = self.lifecycle.state
        if state is None:
            raise GameLifecycleError("LocalGameSession event stream requires a started lifecycle.")
        if viewer.viewer_player_id is not None and viewer.viewer_player_id not in state.player_ids:
            raise GameLifecycleError("Viewer context player is not part of this game.")

    def replay_artifact(self, *, artifact_id: str) -> ReplayArtifactPayload:
        initial_payload = self._initial_replay_lifecycle_payload
        if initial_payload is None:
            if self.lifecycle.state is None:
                raise GameLifecycleError("LocalGameSession replay export requires a started game.")
            if self.lifecycle.decision_controller.records:
                raise GameLifecycleError(
                    "LocalGameSession replay export requires an initial replay snapshot."
                )
            initial_payload = _lifecycle_payload_copy(self.lifecycle)
        return ReplayArtifact.capture(
            artifact_id=artifact_id,
            initial_lifecycle_payload=initial_payload,
            final_lifecycle=self.lifecycle,
        ).to_payload()

    def support_profile(self) -> SupportProfilePayload:
        return build_support_profile(config=self.lifecycle.config)

    def _capture_initial_replay_lifecycle_if_needed(self, status: LifecycleStatus) -> None:
        if self._initial_replay_lifecycle_payload is not None:
            return
        if self.lifecycle.decision_controller.records:
            return
        if status.status_kind not in {
            LifecycleStatusKind.WAITING_FOR_DECISION,
            LifecycleStatusKind.TERMINAL,
            LifecycleStatusKind.INVALID,
            LifecycleStatusKind.UNSUPPORTED,
        }:
            return
        self._initial_replay_lifecycle_payload = _lifecycle_payload_copy(self.lifecycle)
        self._persistence_payload_cache = None


def _validate_viewer_player_id(
    *,
    lifecycle: GameLifecycle,
    viewer_player_id: object,
) -> str:
    state = lifecycle.state
    if state is None:
        raise GameLifecycleError("LocalGameSession event stream requires a started lifecycle.")
    if type(viewer_player_id) is not str:
        raise GameLifecycleError("viewer_player_id must be a string.")
    viewer = viewer_player_id.strip()
    if not viewer:
        raise GameLifecycleError("viewer_player_id must not be empty.")
    if viewer not in state.player_ids:
        raise GameLifecycleError("viewer_player_id must be a player in this game.")
    return viewer


def _lifecycle_payload_copy(lifecycle: GameLifecycle) -> GameLifecyclePayload:
    if type(lifecycle) is not GameLifecycle:
        raise GameLifecycleError("LocalGameSession replay snapshot requires GameLifecycle.")
    return copy.deepcopy(lifecycle.to_payload())


def _persistence_object(payload: JsonValue) -> dict[str, JsonValue]:
    try:
        validated = validate_json_value(copy.deepcopy(payload))
    except EventLogError as exc:
        raise LocalGameSessionPersistenceError(
            "LocalGameSession persistence payload is not JSON-safe."
        ) from exc
    if not isinstance(validated, dict):
        raise LocalGameSessionPersistenceError(
            "LocalGameSession persistence payload must be an object."
        )
    return validated


def _current_rng_state(lifecycle: GameLifecycle) -> RandomSourcePayload:
    if type(lifecycle) is not GameLifecycle or lifecycle.state is None:
        raise LocalGameSessionPersistenceError(
            "LocalGameSession persistence RNG state requires a started lifecycle."
        )
    try:
        manager = DiceRollManager(
            lifecycle.state.game_id,
            event_log=lifecycle.decision_controller.event_log,
        )
    except (DecisionError, EventLogError) as exc:
        raise LocalGameSessionPersistenceError(
            "LocalGameSession persistence RNG reconstruction failed."
        ) from exc
    return manager.rng.to_payload()


def _decision_records_hash(lifecycle: GameLifecycle) -> str:
    if type(lifecycle) is not GameLifecycle:
        raise LocalGameSessionPersistenceError(
            "LocalGameSession decision hash requires GameLifecycle."
        )
    payload = [record.to_payload() for record in lifecycle.decision_controller.records]
    return _payload_sha256(cast(JsonValue, payload))


def _verify_persistence_replay(
    *,
    artifact: ReplayArtifact,
    expected_lifecycle: GameLifecycle,
) -> None:
    try:
        initial_lifecycle = GameLifecycle.from_payload(
            copy.deepcopy(artifact.initial_lifecycle_payload)
        )
        replay_session = LocalGameSession(lifecycle=initial_lifecycle)
        initial_decision_count = len(initial_lifecycle.decision_controller.records)
        initial_event_count = len(initial_lifecycle.decision_controller.event_log.records)
        expected_decision_tail = tuple(
            expected_lifecycle.decision_controller.records[initial_decision_count:]
        )
        expected_event_tail = tuple(
            expected_lifecycle.decision_controller.event_log.records[initial_event_count:]
        )
        if not _payloads_match_exactly(
            cast(JsonValue, [record.to_payload() for record in artifact.decision_records]),
            cast(JsonValue, [record.to_payload() for record in expected_decision_tail]),
        ):
            raise LocalGameSessionPersistenceError(
                "LocalGameSession persistence replay decision tail drifted."
            )
        if not _payloads_match_exactly(
            cast(JsonValue, [record.to_payload() for record in artifact.event_records]),
            cast(JsonValue, [record.to_payload() for record in expected_event_tail]),
        ):
            raise LocalGameSessionPersistenceError(
                "LocalGameSession persistence replay event tail drifted."
            )
        for record_offset, record in enumerate(artifact.decision_records):
            absolute_record_index = initial_decision_count + record_offset
            if _persistence_replay_record_already_reproduced(
                lifecycle=replay_session.lifecycle,
                expected_record=record,
                absolute_record_index=absolute_record_index,
            ):
                continue
            status = submit_replay_record(session=replay_session, record=record)
            if status.status_kind is LifecycleStatusKind.ADVANCED:
                status = replay_session.advance_until_decision_or_terminal()
                if status.status_kind is LifecycleStatusKind.ADVANCED:
                    raise LocalGameSessionPersistenceError(
                        "LocalGameSession replay did not reach a visible lifecycle boundary."
                    )
            if not _persistence_replay_record_already_reproduced(
                lifecycle=replay_session.lifecycle,
                expected_record=record,
                absolute_record_index=absolute_record_index,
            ):
                raise LocalGameSessionPersistenceError(
                    "LocalGameSession persistence replay did not reproduce its decision record."
                )
    except (DecisionError, GameLifecycleError) as exc:
        raise LocalGameSessionPersistenceError(
            "LocalGameSession persistence replay submission failed."
        ) from exc
    if not _payloads_match_exactly(
        cast(JsonValue, replay_session.lifecycle.to_payload()),
        cast(JsonValue, expected_lifecycle.to_payload()),
    ):
        raise LocalGameSessionPersistenceError(
            "LocalGameSession persistence replay lifecycle drifted."
        )


def _persistence_replay_record_already_reproduced(
    *,
    lifecycle: GameLifecycle,
    expected_record: DecisionRecord,
    absolute_record_index: int,
) -> bool:
    records = lifecycle.decision_controller.records
    if len(records) < absolute_record_index:
        raise LocalGameSessionPersistenceError(
            "LocalGameSession persistence replay decision record sequence drifted."
        )
    if len(records) == absolute_record_index:
        return False
    actual_record = records[absolute_record_index]
    if not _payloads_match_exactly(
        cast(JsonValue, actual_record.to_payload()),
        cast(JsonValue, expected_record.to_payload()),
    ):
        raise LocalGameSessionPersistenceError(
            "LocalGameSession persistence automatically reproduced decision record drifted."
        )
    return True


def _require_payload_hash(*, field_name: str, stored: object, actual: str) -> None:
    expected = _persistence_sha256(field_name, stored)
    if expected != actual:
        raise LocalGameSessionPersistenceError(
            f"LocalGameSession persistence {field_name} drifted."
        )


def _payload_sha256(payload: JsonValue) -> str:
    return hashlib.sha256(canonical_json(payload).encode("utf-8")).hexdigest()


def _payloads_match_exactly(left: JsonValue, right: JsonValue) -> bool:
    return canonical_json(left) == canonical_json(right)


def _persistence_sha256(field_name: str, value: object) -> str:
    if type(value) is not str or len(value) != 64:
        raise LocalGameSessionPersistenceError(
            f"LocalGameSession persistence {field_name} is not a SHA-256 digest."
        )
    if any(character not in "0123456789abcdef" for character in value):
        raise LocalGameSessionPersistenceError(
            f"LocalGameSession persistence {field_name} is not lowercase SHA-256."
        )
    return value
