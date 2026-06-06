from __future__ import annotations

import json
import re
from html.parser import HTMLParser
from typing import Any


class TextAndLinkParser(HTMLParser):
    def __init__(self) -> None:
        super().__init__()
        self.title = ""
        self._in_title = False
        self.text_parts: list[str] = []
        self.links: list[dict[str, str]] = []

    def handle_starttag(self, tag: str, attrs: list[tuple[str, str | None]]) -> None:
        if tag.lower() == "title":
            self._in_title = True
        if tag.lower() == "a":
            attrs_dict = dict(attrs)
            href = attrs_dict.get("href")
            if href:
                self.links.append({"href": href, "text": ""})

    def handle_endtag(self, tag: str) -> None:
        if tag.lower() == "title":
            self._in_title = False

    def handle_data(self, data: str) -> None:
        text = " ".join(data.split())
        if not text:
            return
        if self._in_title:
            self.title = f"{self.title} {text}".strip()
        else:
            self.text_parts.append(text)
            if self.links and not self.links[-1]["text"]:
                self.links[-1]["text"] = text[:120]


def extract_structured_data(html: str, url: str = "") -> dict[str, Any]:
    parser = TextAndLinkParser()
    parser.feed(html)
    text = " ".join(parser.text_parts)
    json_ld = _extract_json_ld(html)
    return {
        "url": url,
        "title": parser.title,
        "summary_text": text[:2500],
        "links": parser.links[:40],
        "json_ld": json_ld[:10],
        "word_count": len(text.split()),
    }


def _extract_json_ld(html: str) -> list[Any]:
    blocks: list[Any] = []
    pattern = re.compile(
        r"<script[^>]+type=[\"']application/ld\+json[\"'][^>]*>(.*?)</script>",
        flags=re.IGNORECASE | re.DOTALL,
    )
    for match in pattern.finditer(html):
        raw = match.group(1).strip()
        try:
            blocks.append(json.loads(raw))
        except json.JSONDecodeError:
            blocks.append({"unparsed": raw[:1000]})
    return blocks
