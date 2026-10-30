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


def resolve_streamed_structure(root: HtmlNode) -> HtmlNode:
    """Place streamed markup at its template slot, preserving scalar value readers."""
    targets = {
        node.attrs["id"]: node for node in walk(root) if node.attrs.get("id", "").startswith("S:")
    }

    def resolve(node: HtmlNode, active: tuple[str, ...]) -> HtmlNode:
        children: list[HtmlNode | str] = []
        for child in node.children:
            if isinstance(child, str):
                children.append(child)
                continue
            if child.attrs.get("id", "").startswith("S:"):
                continue
            if child.tag == "template":
                template_id = child.attrs.get("id", "")
                target_id = "S:" + template_id.partition(":")[2]
                target = targets.get(target_id)
                if target is not None and direct_node_children(target):
                    if target_id in active:
                        raise MfmSourceError("MFM streamed structure contains a template cycle.")
                    children.extend(resolve(target, (*active, target_id)).children)
                    continue
            children.append(resolve(child, active))
        return HtmlNode(node.tag, dict(node.attrs), children)

    return resolve(root, ())


def enhancement_wrappers(section: HtmlNode) -> tuple[HtmlNode, ...]:
    """Normalize legacy wrappers and current sibling allowance rows once at import."""
    wrappers: list[HtmlNode] = []
    for listing in walk(section, tag="ul"):
        for child in direct_node_children(listing):
            if child.tag == "div" and any(row.tag == "li" for row in direct_node_children(child)):
                wrappers.append(child)
            elif child.tag == "li":
                spans = walk(child, tag="span")
                if spans and node_text(spans[0]).upper() in {"LEADER:", "SUPPORT:"}:
                    if not wrappers:
                        raise MfmSourceError("MFM enhancement allowance has no enhancement.")
                    previous = wrappers[-1]
                    wrappers[-1] = HtmlNode(
                        "div", {}, [*previous.children, HtmlNode("div", {}, child.children)]
                    )
                else:
                    wrappers.append(HtmlNode("div", {}, [child]))
    if not wrappers:
        raise MfmSourceError("MFM enhancement section contains no price rows.")
    return tuple(wrappers)


def template_texts(template_nodes: dict[str, HtmlNode]) -> dict[str, str]:
    texts: dict[str, str] = {}
    for template_id, node in template_nodes.items():
        text = node_text(node)
        if not text:
            continue
        texts[template_id] = text
    if not texts:
        raise MfmSourceError("MFM page did not contain streamed template values.")
    return texts
