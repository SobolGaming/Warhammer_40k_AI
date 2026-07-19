from __future__ import annotations

import json
from http import HTTPStatus
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
from typing import ClassVar
from urllib.parse import parse_qs, urlparse

from warhammer40k_core.adapters.server import AdapterGameServer
from warhammer40k_core.adapters.server_types import ServerApiError, ServerResponse
from warhammer40k_core.engine.event_log import EventLogError, JsonValue, validate_json_value


def create_http_server(
    *,
    host: str,
    port: int,
    api: AdapterGameServer,
) -> ThreadingHTTPServer:
    return ThreadingHTTPServer((host, port), _handler_for_api(api))


def _handler_for_api(api: AdapterGameServer) -> type[BaseHTTPRequestHandler]:
    class AdapterGameRequestHandler(BaseHTTPRequestHandler):
        server_version = "COREV2AdapterGameHTTP/0.1"
        _api: ClassVar[AdapterGameServer] = api

        def do_GET(self) -> None:
            self._send_api_response(body=None)

        def do_POST(self) -> None:
            try:
                body = self._read_json_body()
            except ServerApiError as exc:
                self._write_response(exc.to_response())
                return
            self._send_api_response(body=body)

        def _send_api_response(self, *, body: JsonValue) -> None:
            parsed = urlparse(self.path)
            try:
                query = _single_value_query(parsed.query)
            except ServerApiError as exc:
                self._write_response(exc.to_response())
                return
            response = self._api.handle(
                method=self.command,
                path=parsed.path,
                query=query,
                body=body,
                authorization=self.headers.get("Authorization"),
            )
            self._write_response(response)

        def _write_response(self, response: ServerResponse) -> None:
            encoded = json.dumps(response.payload, sort_keys=True).encode("utf-8")
            self.send_response(response.status_code)
            self.send_header("Content-Type", "application/json")
            self.send_header("Content-Length", str(len(encoded)))
            self.end_headers()
            self.wfile.write(encoded)

        def _read_json_body(self) -> JsonValue:
            length_header = self.headers.get("Content-Length")
            if length_header is None:
                return None
            length = _parse_content_length(length_header)
            if length == 0:
                return None
            raw_body = self.rfile.read(length)
            try:
                decoded = raw_body.decode("utf-8")
            except UnicodeDecodeError as exc:
                raise ServerApiError(
                    status_code=HTTPStatus.BAD_REQUEST,
                    code="malformed_json_body",
                    message="Request body must be UTF-8 JSON.",
                ) from exc
            try:
                return validate_json_value(json.loads(decoded))
            except json.JSONDecodeError as exc:
                raise ServerApiError(
                    status_code=HTTPStatus.BAD_REQUEST,
                    code="malformed_json_body",
                    message="Request body must be valid JSON.",
                ) from exc
            except EventLogError as exc:
                raise ServerApiError(
                    status_code=HTTPStatus.BAD_REQUEST,
                    code="malformed_json_payload",
                    message="Request body must contain JSON-safe values.",
                ) from exc

    return AdapterGameRequestHandler


def _single_value_query(query: str) -> dict[str, str]:
    parsed = parse_qs(query, keep_blank_values=True)
    values: dict[str, str] = {}
    for key, items in parsed.items():
        if len(items) != 1:
            raise ServerApiError(
                status_code=HTTPStatus.BAD_REQUEST,
                code="ambiguous_query_parameter",
                message="Query parameters must have a single value.",
            )
        values[key] = items[0]
    return values


def _parse_content_length(value: str) -> int:
    stripped = value.strip()
    if not stripped.isdecimal():
        raise ServerApiError(
            status_code=HTTPStatus.BAD_REQUEST,
            code="invalid_content_length",
            message="Content-Length must be a non-negative integer.",
        )
    return int(stripped)
