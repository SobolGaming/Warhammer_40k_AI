from __future__ import annotations

from dataclasses import dataclass
from html.parser import HTMLParser

from warhammer40k_core.rules.mfm_validation import MfmSourceError
from warhammer40k_core.rules.text_normalization import normalize_source_label

_VOID_TAGS = frozenset(
    (
        "area",
        "base",
        "br",
        "col",
        "embed",
        "hr",
        "img",
        "input",
        "link",
        "meta",
        "param",
        "source",
        "track",
        "wbr",
    )
)


@dataclass(slots=True)
class HtmlNode:
    tag: str
    attrs: dict[str, str]
    children: list[HtmlNode | str]


class _MfmHtmlTreeBuilder(HTMLParser):
    def __init__(self) -> None:
        super().__init__(convert_charrefs=True)
        self.root = HtmlNode(tag="document", attrs={}, children=[])
        self._stack: list[HtmlNode] = [self.root]

    def handle_starttag(self, tag: str, attrs: list[tuple[str, str | None]]) -> None:
        normalized_tag = tag.lower()
        node = HtmlNode(
            tag=normalized_tag,
            attrs={key: "" if value is None else value for key, value in attrs},
            children=[],
        )
        self._stack[-1].children.append(node)
        if normalized_tag not in _VOID_TAGS:
            self._stack.append(node)

    def handle_startendtag(self, tag: str, attrs: list[tuple[str, str | None]]) -> None:
        normalized_tag = tag.lower()
        self._stack[-1].children.append(
            HtmlNode(
                tag=normalized_tag,
                attrs={key: "" if value is None else value for key, value in attrs},
                children=[],
            )
        )

    def handle_endtag(self, tag: str) -> None:
        normalized_tag = tag.lower()
        if normalized_tag in _VOID_TAGS:
            return
        if len(self._stack) == 1 or self._stack[-1].tag != normalized_tag:
            raise MfmSourceError("MFM HTML contains mismatched tags.")
        self._stack.pop()

    def handle_data(self, data: str) -> None:
        if data:
            self._stack[-1].children.append(data)

    def has_open_tags(self) -> bool:
        return len(self._stack) != 1


def parse_html(html: str) -> HtmlNode:
    if type(html) is not str:
        raise MfmSourceError("MFM HTML must be a string.")
    if not html.strip():
        raise MfmSourceError("MFM HTML must not be empty.")
    parser = _MfmHtmlTreeBuilder()
    parser.feed(html)
    parser.close()
    if parser.has_open_tags():
        raise MfmSourceError("MFM HTML ended with unclosed tags.")
    return parser.root


def walk(node: HtmlNode, *, tag: str | None = None) -> tuple[HtmlNode, ...]:
    found: list[HtmlNode] = []
    for child in node.children:
        if type(child) is not HtmlNode:
            continue
        if tag is None or child.tag == tag:
            found.append(child)
        found.extend(walk(child, tag=tag))
    return tuple(found)


def direct_node_children(node: HtmlNode) -> tuple[HtmlNode, ...]:
    return tuple(child for child in node.children if type(child) is HtmlNode)


def first_direct_node_child(node: HtmlNode) -> HtmlNode | None:
    for child in node.children:
        if type(child) is HtmlNode:
            return child
    return None


def node_text(node: HtmlNode) -> str:
    parts: list[str] = []
    for child in node.children:
        if type(child) is str:
            parts.append(child)
        elif type(child) is HtmlNode:
            parts.append(node_text(child))
    raw_text = " ".join(part for part in parts if part.strip())
    if not raw_text.strip():
        return ""
    return normalize_source_label(raw_text)


def node_has_class_tokens(node: HtmlNode, tokens: frozenset[str]) -> bool:
    class_value = node.attrs.get("class", "")
    classes = frozenset(class_value.split())
    return tokens.issubset(classes)


def node_has_class_token(node: HtmlNode, token: str) -> bool:
    return token in node.attrs.get("class", "").split()


def node_contains_template(node: HtmlNode) -> bool:
    return any(child.tag == "template" for child in walk(node))
