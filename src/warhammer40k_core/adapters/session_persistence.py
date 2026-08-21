from __future__ import annotations

import hashlib
import json
import sqlite3
from contextlib import closing
from dataclasses import dataclass
from pathlib import Path
from typing import Protocol, cast, runtime_checkable

from warhammer40k_core.engine.event_log import (
    EventLogError,
    JsonValue,
    canonical_json,
    validate_json_value,
)

SESSION_PERSISTENCE_STORE_SCHEMA_VERSION = "server-persistence-store-v1"
SQLITE_SESSION_STATE_TABLE = "session_persistence_state"
_SQLITE_USER_VERSION = 1
_SQLITE_BUSY_TIMEOUT_MILLISECONDS = 30_000


class SessionPersistenceError(ValueError):
    """Raised when durable server-session state cannot be stored or loaded safely."""


class SessionPersistenceCorruptionError(SessionPersistenceError):
    """Raised when persisted bytes fail their closed shape or integrity hash."""


class SessionPersistenceDriftError(SessionPersistenceError):
    """Raised when the durable store schema is not the exact supported schema."""


class SessionPersistenceStorageError(SessionPersistenceError):
    """Raised when SQLite cannot complete the requested durable operation."""


@runtime_checkable
class SessionPersistenceStore(Protocol):
    def load(self) -> JsonValue | None:
        """Load the complete authoritative server payload, or legal first-boot absence."""
        ...

    def commit(self, payload: JsonValue) -> None:
        """Atomically replace the complete authoritative server payload."""
        ...


@dataclass(frozen=True, slots=True)
class SQLiteSessionPersistenceStore:
    """One-row, fail-closed SQLite store for a complete authoritative server payload."""

    database_path: Path

    def __post_init__(self) -> None:
        path = _database_path(self.database_path)
        resolved = path.resolve(strict=False)
        if not resolved.parent.is_dir():
            raise SessionPersistenceStorageError(
                "SQLite persistence database parent directory does not exist."
            )
        if resolved.exists() and not resolved.is_file():
            raise SessionPersistenceStorageError(
                "SQLite persistence database path is not a regular file."
            )
        object.__setattr__(self, "database_path", resolved)
        self._initialize()

    def load(self) -> JsonValue | None:
        with closing(self._connect()) as connection:
            self._validate_database_schema(connection)
            try:
                rows = connection.execute(
                    f"SELECT singleton_id, schema_version, payload_json, content_hash "
                    f"FROM {SQLITE_SESSION_STATE_TABLE} ORDER BY singleton_id"
                ).fetchall()
            except sqlite3.OperationalError as exc:
                raise SessionPersistenceStorageError(
                    "SQLite persistence load could not read server state."
                ) from exc
            except sqlite3.DatabaseError as exc:
                raise SessionPersistenceCorruptionError(
                    "SQLite persistence database is corrupt."
                ) from exc
        if not rows:
            return None
        if len(rows) != 1:
            raise SessionPersistenceCorruptionError(
                "SQLite persistence requires exactly one singleton server-state row."
            )
        singleton_id, schema_version, payload_json, content_hash = rows[0]
        if singleton_id != 1:
            raise SessionPersistenceCorruptionError(
                "SQLite persistence singleton identifier is invalid."
            )
        if schema_version != SESSION_PERSISTENCE_STORE_SCHEMA_VERSION:
            raise SessionPersistenceDriftError("SQLite persistence payload schema version drifted.")
        if type(payload_json) is not str or type(content_hash) is not str:
            raise SessionPersistenceCorruptionError(
                "SQLite persistence row contains invalid storage types."
            )
        payload = _decode_canonical_payload(payload_json)
        if _payload_sha256(payload) != _validate_sha256(content_hash):
            raise SessionPersistenceCorruptionError(
                "SQLite persistence payload content hash does not match."
            )
        return payload

    def commit(self, payload: JsonValue) -> None:
        validated = _validated_json(payload)
        payload_json = canonical_json(validated)
        content_hash = _text_sha256(payload_json)
        with closing(self._connect()) as connection:
            self._validate_database_schema(connection)
            try:
                connection.execute("BEGIN IMMEDIATE")
                connection.execute(
                    f"INSERT INTO {SQLITE_SESSION_STATE_TABLE} "
                    "(singleton_id, schema_version, payload_json, content_hash) "
                    "VALUES (1, ?, ?, ?) "
                    "ON CONFLICT(singleton_id) DO UPDATE SET "
                    "schema_version=excluded.schema_version, "
                    "payload_json=excluded.payload_json, "
                    "content_hash=excluded.content_hash",
                    (
                        SESSION_PERSISTENCE_STORE_SCHEMA_VERSION,
                        payload_json,
                        content_hash,
                    ),
                )
                connection.commit()
            except sqlite3.IntegrityError as exc:
                connection.rollback()
                raise SessionPersistenceCorruptionError(
                    "SQLite persistence singleton constraints were violated."
                ) from exc
            except sqlite3.OperationalError as exc:
                connection.rollback()
                raise SessionPersistenceStorageError(
                    "SQLite persistence commit did not complete."
                ) from exc
            except sqlite3.DatabaseError as exc:
                connection.rollback()
                raise SessionPersistenceCorruptionError(
                    "SQLite persistence database is corrupt."
                ) from exc

    def _initialize(self) -> None:
        with closing(self._connect()) as connection:
            try:
                connection.execute("PRAGMA journal_mode=WAL")
                connection.execute("PRAGMA synchronous=FULL")
                table_names = _user_table_names(connection)
                user_version = _sqlite_user_version(connection)
            except sqlite3.OperationalError as exc:
                raise SessionPersistenceStorageError(
                    "SQLite persistence database could not be inspected."
                ) from exc
            except sqlite3.DatabaseError as exc:
                raise SessionPersistenceCorruptionError(
                    "SQLite persistence database is corrupt."
                ) from exc
            create_schema = _database_requires_initialization(
                table_names=table_names,
                user_version=user_version,
            )
            try:
                connection.execute("BEGIN IMMEDIATE")
                if create_schema:
                    connection.execute(
                        f"CREATE TABLE {SQLITE_SESSION_STATE_TABLE} ("
                        "singleton_id INTEGER NOT NULL PRIMARY KEY "
                        "CHECK(singleton_id = 1), "
                        "schema_version TEXT NOT NULL, "
                        "payload_json TEXT NOT NULL, "
                        "content_hash TEXT NOT NULL"
                        ") STRICT"
                    )
                    connection.execute(f"PRAGMA user_version={_SQLITE_USER_VERSION}")
                connection.commit()
            except sqlite3.IntegrityError as exc:
                connection.rollback()
                raise SessionPersistenceCorruptionError(
                    "SQLite persistence schema constraints are invalid."
                ) from exc
            except sqlite3.OperationalError as exc:
                connection.rollback()
                raise SessionPersistenceStorageError(
                    "SQLite persistence database could not be initialized."
                ) from exc
            except sqlite3.DatabaseError as exc:
                connection.rollback()
                raise SessionPersistenceCorruptionError(
                    "SQLite persistence database is corrupt."
                ) from exc
        with closing(self._connect()) as connection:
            self._validate_database_schema(connection)

    def _connect(self) -> sqlite3.Connection:
        connection: sqlite3.Connection | None = None
        try:
            connection = sqlite3.connect(
                self.database_path,
                timeout=_SQLITE_BUSY_TIMEOUT_MILLISECONDS / 1000,
            )
            connection.execute(f"PRAGMA busy_timeout={_SQLITE_BUSY_TIMEOUT_MILLISECONDS}")
            connection.execute("PRAGMA synchronous=FULL")
        except sqlite3.OperationalError as exc:
            if connection is not None:
                connection.close()
            raise SessionPersistenceStorageError(
                "SQLite persistence database could not be opened."
            ) from exc
        except sqlite3.DatabaseError as exc:
            if connection is not None:
                connection.close()
            raise SessionPersistenceCorruptionError(
                "SQLite persistence database is corrupt."
            ) from exc
        return connection

    def _validate_database_schema(self, connection: sqlite3.Connection) -> None:
        try:
            user_version = _sqlite_user_version(connection)
            table_names = _user_table_names(connection)
            columns = tuple(
                (row[1], row[2], row[3], row[5])
                for row in connection.execute(
                    f"PRAGMA table_info({SQLITE_SESSION_STATE_TABLE})"
                ).fetchall()
            )
        except sqlite3.OperationalError as exc:
            raise SessionPersistenceStorageError(
                "SQLite persistence schema could not be inspected."
            ) from exc
        except sqlite3.DatabaseError as exc:
            raise SessionPersistenceCorruptionError(
                "SQLite persistence database is corrupt."
            ) from exc
        if user_version != _SQLITE_USER_VERSION:
            raise SessionPersistenceDriftError(
                "SQLite persistence database schema version drifted."
            )
        if table_names != (SQLITE_SESSION_STATE_TABLE,):
            raise SessionPersistenceDriftError("SQLite persistence database table set drifted.")
        expected = (
            ("singleton_id", "INTEGER", 1, 1),
            ("schema_version", "TEXT", 1, 0),
            ("payload_json", "TEXT", 1, 0),
            ("content_hash", "TEXT", 1, 0),
        )
        if columns != expected:
            raise SessionPersistenceDriftError("SQLite persistence database column schema drifted.")


def _database_requires_initialization(
    *,
    table_names: tuple[str, ...],
    user_version: int,
) -> bool:
    if not table_names:
        if user_version != 0:
            raise SessionPersistenceDriftError(
                "SQLite persistence user version exists without its state table."
            )
        return True
    if table_names != (SQLITE_SESSION_STATE_TABLE,):
        raise SessionPersistenceDriftError(
            "SQLite persistence database contains an unsupported table set."
        )
    return False


def _database_path(value: object) -> Path:
    if not isinstance(value, Path):
        raise SessionPersistenceStorageError(
            "SQLite persistence database path must be a pathlib.Path."
        )
    return value


def _user_table_names(connection: sqlite3.Connection) -> tuple[str, ...]:
    rows = cast(
        list[tuple[object, ...]],
        connection.execute(
            "SELECT name FROM sqlite_schema "
            "WHERE type = 'table' AND name NOT LIKE 'sqlite_%' ORDER BY name"
        ).fetchall(),
    )
    names: list[str] = []
    for row in rows:
        if type(row) is not tuple or len(row) != 1 or type(row[0]) is not str:
            raise SessionPersistenceCorruptionError("SQLite persistence table metadata is invalid.")
        names.append(row[0])
    return tuple(names)


def _sqlite_user_version(connection: sqlite3.Connection) -> int:
    row = cast(tuple[object, ...] | None, connection.execute("PRAGMA user_version").fetchone())
    if type(row) is not tuple or len(row) != 1 or type(row[0]) is not int:
        raise SessionPersistenceCorruptionError(
            "SQLite persistence user-version metadata is invalid."
        )
    return row[0]


def _decode_canonical_payload(payload_json: str) -> JsonValue:
    try:
        decoded: object = json.loads(payload_json)
    except json.JSONDecodeError as exc:
        raise SessionPersistenceCorruptionError(
            "SQLite persistence payload is not valid JSON."
        ) from exc
    try:
        payload = validate_json_value(decoded)
    except EventLogError as exc:
        raise SessionPersistenceCorruptionError(
            "SQLite persistence payload is not a valid JSON value."
        ) from exc
    if canonical_json(payload) != payload_json:
        raise SessionPersistenceCorruptionError(
            "SQLite persistence payload is not canonically encoded."
        )
    return payload


def _validated_json(payload: JsonValue) -> JsonValue:
    try:
        return validate_json_value(payload)
    except EventLogError as exc:
        raise SessionPersistenceError(
            "Session persistence commit requires a JSON-safe payload."
        ) from exc


def _payload_sha256(payload: JsonValue) -> str:
    return _text_sha256(canonical_json(payload))


def _text_sha256(value: str) -> str:
    return hashlib.sha256(value.encode("utf-8")).hexdigest()


def _validate_sha256(value: object) -> str:
    if type(value) is not str or len(value) != 64:
        raise SessionPersistenceCorruptionError(
            "SQLite persistence content hash is not a SHA-256 digest."
        )
    if any(character not in "0123456789abcdef" for character in value):
        raise SessionPersistenceCorruptionError(
            "SQLite persistence content hash is not a lowercase SHA-256 digest."
        )
    return value


__all__ = [
    "SESSION_PERSISTENCE_STORE_SCHEMA_VERSION",
    "SQLITE_SESSION_STATE_TABLE",
    "SQLiteSessionPersistenceStore",
    "SessionPersistenceCorruptionError",
    "SessionPersistenceDriftError",
    "SessionPersistenceError",
    "SessionPersistenceStorageError",
    "SessionPersistenceStore",
]
