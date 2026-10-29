"""Obsidian notes: frontmatter and the generated block inkd owns.

inkd only ever rewrites the text between its two markers and its own `inkd_*`
frontmatter keys; everything else in a note belongs to the user.
"""

from __future__ import annotations

import hashlib
import re
from dataclasses import dataclass
from pathlib import Path

import yaml

BEGIN = "<!-- inkd:begin (written by inkd from the reMarkable; edits in here are replaced) -->"
END = "<!-- inkd:end -->"
_BLOCK = re.compile(r"\n?<!-- inkd:begin.*?-->.*?<!-- inkd:end -->\n?", re.S)
_FRONTMATTER = re.compile(r"\A---\n(.*?)\n---\n?", re.S)


@dataclass
class Note:
    meta: dict
    body: str

    @classmethod
    def parse(cls, text: str) -> "Note":
        m = _FRONTMATTER.match(text)
        if not m:
            return cls({}, text)
        meta = yaml.safe_load(m.group(1)) or {}
        if not isinstance(meta, dict):
            return cls({}, text)
        return cls(meta, text[m.end():])

    @classmethod
    def read(cls, path: Path) -> "Note":
        return cls.parse(path.read_text(encoding="utf-8")) if path.exists() else cls({}, "")

    def render(self) -> str:
        if not self.meta:
            return self.body
        fm = yaml.safe_dump(self.meta, allow_unicode=True, sort_keys=False).strip()
        return f"---\n{fm}\n---\n{self.body}"

    def write(self, path: Path) -> None:
        path.parent.mkdir(parents=True, exist_ok=True)
        path.write_text(self.render(), encoding="utf-8")

    def user_body(self) -> str:
        """The body without inkd's block: what gets published to the tablet."""
        return _BLOCK.sub("\n", self.body).strip() + "\n"

    def user_hash(self) -> str:
        user_meta = {k: v for k, v in self.meta.items() if not str(k).startswith("inkd_")}
        payload = yaml.safe_dump(user_meta, sort_keys=True) + self.user_body()
        return hashlib.sha256(payload.encode()).hexdigest()

    def set_block(self, content: str) -> None:
        block = f"{BEGIN}\n{content.strip()}\n{END}\n"
        if _BLOCK.search(self.body):
            self.body = _BLOCK.sub(lambda _: "\n" + block, self.body, count=1)
        else:
            self.body = self.body.rstrip() + ("\n\n" if self.body.strip() else "") + block


@dataclass
class PageText:
    number: int  # 1-based
    image: str  # vault-relative path of the page image
    text: str


def block_for_pages(pages: list[PageText], heading: str | None = None) -> str:
    parts = [f"## {heading}"] if heading else []
    for p in pages:
        parts.append(f"### Page {p.number}\n\n![[{p.image}]]\n\n{p.text.strip()}".rstrip())
    return "\n\n".join(parts)


def safe_name(name: str) -> str:
    """A file name Obsidian accepts on every platform."""
    name = re.sub(r'[\\/:*?"<>|#^\[\]]', "-", name).strip(" .")
    return name or "Untitled"
