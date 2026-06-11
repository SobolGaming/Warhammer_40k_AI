from __future__ import annotations

import re
from dataclasses import dataclass
from html.parser import HTMLParser
from typing import Self, TypedDict


class SourceHtmlSanitizationError(ValueError):
    """Raised when source HTML cannot be sanitized at the ingest boundary."""


class SourceHtmlSanitizationReportPayload(TypedDict):
    source_id: str
    raw_html: str
    sanitized_text: str
    converted_tags: list[str]
    stripped_tags: list[str]
    embedded_links: list[str]


_HTML_TAG_RE = re.compile(r"</?[A-Za-z][^>]*>")
_HORIZONTAL_WHITESPACE_RE = re.compile(r"[ \t\f\v]+")
_NEWLINE_PADDING_RE = re.compile(r" *\n *")
_EXCESS_NEWLINES_RE = re.compile(r"\n{3,}")

_INLINE_TAGS = {
    "a",
    "abbr",
    "b",
    "cite",
    "em",
    "i",
    "span",
    "strong",
    "sub",
    "sup",
    "table",
    "u",
}
_BLOCK_TAGS = {"blockquote", "div", "p", "section"}
_TABLE_CELL_TAGS = {"td", "th"}
_IGNORED_CONTENT_TAGS = {"script", "style"}


@dataclass(frozen=True, slots=True)
class SourceHtmlSanitizationReport:
    source_id: str
    raw_html: str
    sanitized_text: str
    converted_tags: tuple[str, ...]
    stripped_tags: tuple[str, ...] = ()
    embedded_links: tuple[str, ...] = ()

    def __post_init__(self) -> None:
        object.__setattr__(
            self,
            "source_id",
            _validate_identifier("SourceHtmlSanitizationReport source_id", self.source_id),
        )
        if type(self.raw_html) is not str:
            raise SourceHtmlSanitizationError(
                "SourceHtmlSanitizationReport raw_html must be a string."
            )
        if type(self.sanitized_text) is not str:
            raise SourceHtmlSanitizationError(
                "SourceHtmlSanitizationReport sanitized_text must be a string."
            )
        object.__setattr__(
            self,
            "converted_tags",
            _validate_string_tuple(
                "SourceHtmlSanitizationReport converted_tags",
                self.converted_tags,
            ),
        )
        object.__setattr__(
            self,
            "stripped_tags",
            _validate_string_tuple(
                "SourceHtmlSanitizationReport stripped_tags",
                self.stripped_tags,
            ),
        )
        object.__setattr__(
            self,
            "embedded_links",
            _validate_string_tuple(
                "SourceHtmlSanitizationReport embedded_links",
                self.embedded_links,
            ),
        )

    def to_payload(self) -> SourceHtmlSanitizationReportPayload:
        return {
            "source_id": self.source_id,
            "raw_html": self.raw_html,
            "sanitized_text": self.sanitized_text,
            "converted_tags": list(self.converted_tags),
            "stripped_tags": list(self.stripped_tags),
            "embedded_links": list(self.embedded_links),
        }

    @classmethod
    def from_payload(cls, payload: SourceHtmlSanitizationReportPayload) -> Self:
        report = cls(
            source_id=payload["source_id"],
            raw_html=payload["raw_html"],
            sanitized_text=payload["sanitized_text"],
            converted_tags=tuple(payload["converted_tags"]),
            stripped_tags=tuple(payload["stripped_tags"]),
            embedded_links=tuple(payload["embedded_links"]),
        )
        expected = sanitize_source_html(source_id=report.source_id, raw_html=report.raw_html)
        if report.to_payload() != expected.to_payload():
            raise SourceHtmlSanitizationError("SourceHtmlSanitizationReport payload is stale.")
        return report


def sanitize_source_html(*, source_id: object, raw_html: object) -> SourceHtmlSanitizationReport:
    source = _validate_identifier("source_id", source_id)
    if type(raw_html) is not str:
        raise SourceHtmlSanitizationError("raw_html must be a string.")
    parser = _SourceHtmlParser()
    parser.feed(raw_html)
    parser.close()
    sanitized_text = _cleanup_sanitized_text(parser.sanitized_text())
    return SourceHtmlSanitizationReport(
        source_id=source,
        raw_html=raw_html,
        sanitized_text=sanitized_text,
        converted_tags=tuple(parser.converted_tags),
        stripped_tags=tuple(parser.stripped_tags),
        embedded_links=tuple(parser.embedded_links),
    )


def contains_html_markup(text: object) -> bool:
    if type(text) is not str:
        raise SourceHtmlSanitizationError("text must be a string.")
    return _HTML_TAG_RE.search(text) is not None


class _SourceHtmlParser(HTMLParser):
    def __init__(self) -> None:
        super().__init__(convert_charrefs=True)
        self._parts: list[str] = []
        self.converted_tags: list[str] = []
        self.stripped_tags: list[str] = []
        self.embedded_links: list[str] = []
        self._ignored_depth = 0

    def sanitized_text(self) -> str:
        return "".join(self._parts)

    def handle_starttag(self, tag: str, attrs: list[tuple[str, str | None]]) -> None:
        normalized_tag = tag.lower()
        if normalized_tag in _IGNORED_CONTENT_TAGS:
            self._ignored_depth += 1
            self.stripped_tags.append(normalized_tag)
            return
        if self._ignored_depth > 0:
            return
        if normalized_tag == "br":
            self._append_boundary()
            self.converted_tags.append(normalized_tag)
            return
        if normalized_tag == "li":
            self._append_boundary()
            self._parts.append("- ")
            self.converted_tags.append(normalized_tag)
            return
        if normalized_tag in _BLOCK_TAGS or normalized_tag == "tr":
            self._append_boundary()
            self.converted_tags.append(normalized_tag)
            return
        if normalized_tag in _TABLE_CELL_TAGS:
            self._append_cell_separator()
            self.converted_tags.append(normalized_tag)
            return
        if normalized_tag == "a":
            self._record_link(attrs)
            self.converted_tags.append(normalized_tag)
            return
        if normalized_tag in _INLINE_TAGS or normalized_tag in {"ol", "ul", "tbody", "thead"}:
            self.converted_tags.append(normalized_tag)
            return
        self.stripped_tags.append(normalized_tag)

    def handle_startendtag(self, tag: str, attrs: list[tuple[str, str | None]]) -> None:
        self.handle_starttag(tag, attrs)
        if tag.lower() in _BLOCK_TAGS or tag.lower() in {"li", "tr"}:
            self._append_boundary()

    def handle_endtag(self, tag: str) -> None:
        normalized_tag = tag.lower()
        if normalized_tag in _IGNORED_CONTENT_TAGS:
            if self._ignored_depth > 0:
                self._ignored_depth -= 1
            return
        if self._ignored_depth > 0:
            return
        if normalized_tag in _BLOCK_TAGS or normalized_tag in {"li", "tr"}:
            self._append_boundary()
            return
        if normalized_tag in _TABLE_CELL_TAGS:
            self._append_cell_separator()

    def handle_data(self, data: str) -> None:
        if self._ignored_depth == 0:
            self._parts.append(data)

    def _append_boundary(self) -> None:
        if not self._parts:
            return
        if self._parts[-1].endswith("\n"):
            return
        self._parts.append("\n")

    def _append_cell_separator(self) -> None:
        if not self._parts:
            return
        if self._parts[-1].endswith((" ", "\n", "| ")):
            return
        self._parts.append(" | ")

    def _record_link(self, attrs: list[tuple[str, str | None]]) -> None:
        for name, value in attrs:
            if name.lower() == "href" and value is not None and value.strip():
                self.embedded_links.append(value.strip())


def _cleanup_sanitized_text(text: str) -> str:
    cleaned = text.replace("\r\n", "\n").replace("\r", "\n")
    cleaned = _HORIZONTAL_WHITESPACE_RE.sub(" ", cleaned)
    cleaned = _NEWLINE_PADDING_RE.sub("\n", cleaned)
    cleaned = _EXCESS_NEWLINES_RE.sub("\n\n", cleaned)
    return cleaned.strip()


def _validate_identifier(field_name: str, value: object) -> str:
    if type(value) is not str:
        raise SourceHtmlSanitizationError(f"{field_name} must be a string.")
    stripped = value.strip()
    if not stripped:
        raise SourceHtmlSanitizationError(f"{field_name} must not be empty.")
    return stripped


def _validate_string_tuple(field_name: str, values: tuple[str, ...]) -> tuple[str, ...]:
    if type(values) is not tuple:
        raise SourceHtmlSanitizationError(f"{field_name} must be a tuple.")
    validated: list[str] = []
    for value in values:
        validated.append(_validate_identifier(f"{field_name} value", value))
    return tuple(validated)
