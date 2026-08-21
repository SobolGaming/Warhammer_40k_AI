from __future__ import annotations

import hashlib
import json
import os
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

SESSION_PERSISTENCE_STORE_SCHEMA_VERSION = "server-persistence-store-v2"
SQLITE_SESSION_STATE_TABLE = "session_persistence_state"
SQLITE_SESSION_PERSISTENCE_USER_VERSION = 2
_SQLITE_BUSY_TIMEOUT_MILLISECONDS = 30_000
_SQLITE_CREATE_STATE_TABLE_SQL = (
    f"CREATE TABLE {SQLITE_SESSION_STATE_TABLE} ("
    "singleton_id INTEGER NOT NULL PRIMARY KEY CHECK(singleton_id = 1), "
    "schema_version TEXT NOT NULL, "
    "payload_json TEXT NOT NULL, "
    "content_hash TEXT NOT NULL"
    ") STRICT"
)
_SQLITE_EXPECTED_SCHEMA_OBJECTS = (
    (
        "table",
        SQLITE_SESSION_STATE_TABLE,
        SQLITE_SESSION_STATE_TABLE,
        _SQLITE_CREATE_STATE_TABLE_SQL,
    ),
)
_SQLITE_EXPECTED_TABLE_LIST = (
    "main",
    SQLITE_SESSION_STATE_TABLE,
    "table",
    4,
    0,
    1,
)
_SQLITE_EXPECTED_TABLE_XINFO = (
    (0, "singleton_id", "INTEGER", 1, None, 1, 0),
    (1, "schema_version", "TEXT", 1, None, 0, 0),
    (2, "payload_json", "TEXT", 1, None, 0, 0),
    (3, "content_hash", "TEXT", 1, None, 0, 0),
)


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
    def initialize(self, payload: JsonValue) -> None:
        """Create a new store with its first complete authoritative root."""
        ...

    def load(self) -> JsonValue:
        """Load the complete authoritative server payload from an initialized store."""
        ...

    def commit(self, payload: JsonValue) -> None:
        """Atomically replace the complete authoritative server payload."""
        ...


def commit_persistence_store(store: SessionPersistenceStore, payload: JsonValue) -> None:
    """Invoke a custom store through the strict typed commit boundary."""
    if not isinstance(  # pyright: ignore[reportUnnecessaryIsInstance]
        store, SessionPersistenceStore
    ):
        raise SessionPersistenceError("Session persistence store does not conform.")
    try:
        store.commit(payload)
    except (OSError, RuntimeError) as exc:
        raise SessionPersistenceStorageError(
            "Custom persistence commit raised an untyped storage error."
        ) from exc


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

    def initialize(self, payload: JsonValue) -> None:
        """Create this database and its first durable root as one explicit operation."""
        validated = _validated_json(payload)
        payload_json = canonical_json(validated)
        content_hash = _text_sha256(payload_json)
        _create_database_file(self.database_path)
        with closing(self._connect()) as connection:
            try:
                journal_mode = _set_sqlite_wal_mode(connection)
                if journal_mode != "wal":
                    raise SessionPersistenceStorageError(
                        "SQLite persistence database could not enable WAL mode."
                    )
                with connection:
                    connection.execute("BEGIN IMMEDIATE")
                    self._validate_uninitialized_database(connection)
                    connection.execute(_SQLITE_CREATE_STATE_TABLE_SQL)
                    connection.execute(
                        f"PRAGMA user_version={SQLITE_SESSION_PERSISTENCE_USER_VERSION}"
                    )
                    self._validate_database_schema(connection)
                    if _state_rows(connection):
                        raise SessionPersistenceCorruptionError(
                            "SQLite persistence initialization found an unexpected state row."
                        )
                    self._write_and_verify_state_row(
                        connection,
                        payload_json=payload_json,
                        content_hash=content_hash,
                    )
            except SessionPersistenceError:
                raise
            except sqlite3.IntegrityError as exc:
                raise SessionPersistenceCorruptionError(
                    "SQLite persistence initialization constraints were violated."
                ) from exc
            except sqlite3.OperationalError as exc:
                raise SessionPersistenceStorageError(
                    "SQLite persistence database could not be initialized."
                ) from exc
            except sqlite3.DatabaseError as exc:
                raise SessionPersistenceCorruptionError(
                    "SQLite persistence database is corrupt."
                ) from exc

    def load(self) -> JsonValue:
        with closing(self._connect()) as connection:
            try:
                with connection:
                    connection.execute("BEGIN IMMEDIATE")
                    self._validate_database_schema(connection)
                    payload, _row = _read_verified_state_row(connection)
            except SessionPersistenceError:
                raise
            except sqlite3.OperationalError as exc:
                raise SessionPersistenceStorageError(
                    "SQLite persistence load could not read server state."
                ) from exc
            except sqlite3.DatabaseError as exc:
                raise SessionPersistenceCorruptionError(
                    "SQLite persistence database is corrupt."
                ) from exc
        return payload

    def commit(self, payload: JsonValue) -> None:
        validated = _validated_json(payload)
        payload_json = canonical_json(validated)
        content_hash = _text_sha256(payload_json)
        with closing(self._connect()) as connection:
            try:
                with connection:
                    connection.execute("BEGIN IMMEDIATE")
                    self._validate_database_schema(connection)
                    _read_verified_state_row(connection)
                    self._write_and_verify_state_row(
                        connection,
                        payload_json=payload_json,
                        content_hash=content_hash,
                    )
            except SessionPersistenceError:
                raise
            except sqlite3.IntegrityError as exc:
                raise SessionPersistenceCorruptionError(
                    "SQLite persistence singleton constraints were violated."
                ) from exc
            except sqlite3.OperationalError as exc:
                raise SessionPersistenceStorageError(
                    "SQLite persistence commit did not complete."
                ) from exc
            except sqlite3.DatabaseError as exc:
                raise SessionPersistenceCorruptionError(
                    "SQLite persistence database is corrupt."
                ) from exc

    def _connect(self) -> sqlite3.Connection:
        connection: sqlite3.Connection | None = None
        try:
            connection = sqlite3.connect(
                f"{self.database_path.as_uri()}?mode=rw",
                timeout=_SQLITE_BUSY_TIMEOUT_MILLISECONDS / 1000,
                uri=True,
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

    def _validate_uninitialized_database(self, connection: sqlite3.Connection) -> None:
        try:
            user_version = _sqlite_user_version(connection)
            schema_objects = _sqlite_schema_objects(connection)
        except sqlite3.OperationalError as exc:
            raise SessionPersistenceStorageError(
                "SQLite persistence database could not be inspected for initialization."
            ) from exc
        except sqlite3.DatabaseError as exc:
            raise SessionPersistenceCorruptionError(
                "SQLite persistence database is corrupt."
            ) from exc
        if user_version != 0 or schema_objects:
            raise SessionPersistenceDriftError(
                "SQLite persistence initialization requires an empty database."
            )

    def _validate_database_schema(self, connection: sqlite3.Connection) -> None:
        try:
            user_version = _sqlite_user_version(connection)
            journal_mode = _sqlite_journal_mode(connection)
            schema_objects = _sqlite_schema_objects(connection)
            table_list = _sqlite_table_list(connection)
            table_xinfo = _sqlite_table_xinfo(connection)
            index_list = connection.execute(
                f"PRAGMA main.index_list('{SQLITE_SESSION_STATE_TABLE}')"
            ).fetchall()
            foreign_keys = connection.execute(
                f"PRAGMA main.foreign_key_list('{SQLITE_SESSION_STATE_TABLE}')"
            ).fetchall()
        except sqlite3.OperationalError as exc:
            raise SessionPersistenceStorageError(
                "SQLite persistence schema could not be inspected."
            ) from exc
        except sqlite3.DatabaseError as exc:
            raise SessionPersistenceCorruptionError(
                "SQLite persistence database is corrupt."
            ) from exc
        if user_version != SQLITE_SESSION_PERSISTENCE_USER_VERSION:
            raise SessionPersistenceDriftError(
                "SQLite persistence database schema version drifted."
            )
        if journal_mode != "wal":
            raise SessionPersistenceDriftError("SQLite persistence database journal mode drifted.")
        if schema_objects != _SQLITE_EXPECTED_SCHEMA_OBJECTS:
            raise SessionPersistenceDriftError(
                "SQLite persistence database schema objects drifted."
            )
        if table_list != _SQLITE_EXPECTED_TABLE_LIST:
            raise SessionPersistenceDriftError(
                "SQLite persistence database table kind or STRICT mode drifted."
            )
        if table_xinfo != _SQLITE_EXPECTED_TABLE_XINFO:
            raise SessionPersistenceDriftError("SQLite persistence database column schema drifted.")
        if index_list:
            raise SessionPersistenceDriftError("SQLite persistence database index set drifted.")
        if foreign_keys:
            raise SessionPersistenceDriftError(
                "SQLite persistence database foreign-key schema drifted."
            )

    def _write_and_verify_state_row(
        self,
        connection: sqlite3.Connection,
        *,
        payload_json: str,
        content_hash: str,
    ) -> None:
        cursor = connection.execute(
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
        if cursor.rowcount != 1:
            raise SessionPersistenceCorruptionError(
                "SQLite persistence write did not affect its singleton state row."
            )
        _payload, row = _read_verified_state_row(connection)
        expected = (
            1,
            SESSION_PERSISTENCE_STORE_SCHEMA_VERSION,
            payload_json,
            content_hash,
        )
        if row != expected:
            raise SessionPersistenceCorruptionError(
                "SQLite persistence write did not read back exactly."
            )


def _create_database_file(database_path: Path) -> None:
    try:
        descriptor = os.open(database_path, os.O_CREAT | os.O_EXCL | os.O_WRONLY, 0o600)
    except FileExistsError as exc:
        raise SessionPersistenceDriftError(
            "SQLite persistence initialization refuses an existing database path."
        ) from exc
    except OSError as exc:
        raise SessionPersistenceStorageError(
            "SQLite persistence database file could not be created."
        ) from exc
    try:
        os.close(descriptor)
    except OSError as exc:
        raise SessionPersistenceStorageError(
            "SQLite persistence database file could not be closed after creation."
        ) from exc


def _database_path(value: object) -> Path:
    if not isinstance(value, Path):
        raise SessionPersistenceStorageError(
            "SQLite persistence database path must be a pathlib.Path."
        )
    return value


def _sqlite_schema_objects(
    connection: sqlite3.Connection,
) -> tuple[tuple[str, str, str, str], ...]:
    rows = cast(
        list[tuple[object, ...]],
        connection.execute(
            "SELECT type, name, tbl_name, sql FROM main.sqlite_schema ORDER BY type, name, tbl_name"
        ).fetchall(),
    )
    objects: list[tuple[str, str, str, str]] = []
    for row in rows:
        if type(row) is not tuple or len(row) != 4:
            raise SessionPersistenceCorruptionError(
                "SQLite persistence schema-object metadata is invalid."
            )
        object_type, name, table_name, sql = row
        if any(type(value) is not str for value in row):
            raise SessionPersistenceCorruptionError(
                "SQLite persistence schema-object metadata is invalid."
            )
        objects.append(
            (
                cast(str, object_type),
                cast(str, name),
                cast(str, table_name),
                cast(str, sql),
            )
        )
    return tuple(objects)


def _sqlite_table_list(connection: sqlite3.Connection) -> tuple[object, ...]:
    rows = cast(
        list[tuple[object, ...]],
        connection.execute(f"PRAGMA main.table_list('{SQLITE_SESSION_STATE_TABLE}')").fetchall(),
    )
    if not rows:
        return ()
    if len(rows) != 1 or type(rows[0]) is not tuple or len(rows[0]) != 6:
        raise SessionPersistenceCorruptionError(
            "SQLite persistence table-list metadata is invalid."
        )
    return rows[0]


def _sqlite_table_xinfo(
    connection: sqlite3.Connection,
) -> tuple[tuple[object, ...], ...]:
    rows = cast(
        list[tuple[object, ...]],
        connection.execute(f"PRAGMA main.table_xinfo('{SQLITE_SESSION_STATE_TABLE}')").fetchall(),
    )
    if any(type(row) is not tuple or len(row) != 7 for row in rows):
        raise SessionPersistenceCorruptionError(
            "SQLite persistence extended-column metadata is invalid."
        )
    return tuple(rows)


def _sqlite_journal_mode(connection: sqlite3.Connection) -> str:
    row = cast(tuple[object, ...] | None, connection.execute("PRAGMA journal_mode").fetchone())
    if type(row) is not tuple or len(row) != 1 or type(row[0]) is not str:
        raise SessionPersistenceCorruptionError(
            "SQLite persistence journal-mode metadata is invalid."
        )
    return row[0]


def _set_sqlite_wal_mode(connection: sqlite3.Connection) -> str:
    row = cast(
        tuple[object, ...] | None,
        connection.execute("PRAGMA journal_mode=WAL").fetchone(),
    )
    if type(row) is not tuple or len(row) != 1 or type(row[0]) is not str:
        raise SessionPersistenceCorruptionError(
            "SQLite persistence journal-mode initialization result is invalid."
        )
    return row[0]


def _state_rows(connection: sqlite3.Connection) -> list[tuple[object, ...]]:
    return cast(
        list[tuple[object, ...]],
        connection.execute(
            f"SELECT singleton_id, schema_version, payload_json, content_hash "
            f"FROM {SQLITE_SESSION_STATE_TABLE} ORDER BY singleton_id"
        ).fetchall(),
    )


def _read_verified_state_row(
    connection: sqlite3.Connection,
) -> tuple[JsonValue, tuple[int, str, str, str]]:
    rows = _state_rows(connection)
    if len(rows) != 1:
        raise SessionPersistenceCorruptionError(
            "SQLite persistence requires exactly one singleton server-state row."
        )
    row = rows[0]
    if type(row) is not tuple or len(row) != 4:
        raise SessionPersistenceCorruptionError(
            "SQLite persistence row has an invalid storage shape."
        )
    singleton_id, schema_version, payload_json, content_hash = row
    if type(singleton_id) is not int or singleton_id != 1:
        raise SessionPersistenceCorruptionError(
            "SQLite persistence singleton identifier is invalid."
        )
    if type(schema_version) is not str:
        raise SessionPersistenceCorruptionError(
            "SQLite persistence row schema version has an invalid storage type."
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
    return payload, (singleton_id, schema_version, payload_json, content_hash)


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
    "SQLITE_SESSION_PERSISTENCE_USER_VERSION",
    "SQLITE_SESSION_STATE_TABLE",
    "SQLiteSessionPersistenceStore",
    "SessionPersistenceCorruptionError",
    "SessionPersistenceDriftError",
    "SessionPersistenceError",
    "SessionPersistenceStorageError",
    "SessionPersistenceStore",
    "commit_persistence_store",
]
