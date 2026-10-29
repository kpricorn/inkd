"""Obsidian note → PDF laid out for the reMarkable 2 screen."""

from __future__ import annotations

import re
import subprocess
from pathlib import Path

# 1404 x 1872 px at 226 dpi; a wide right margin leaves room for handwriting.
CSS = """
@page { size: 157.8mm 210.4mm; margin: 12mm 30mm 14mm 12mm; }
body { font-family: "DejaVu Serif", Georgia, serif; font-size: 11.5pt; line-height: 1.45; }
h1, h2, h3, h4 { font-family: "DejaVu Sans", sans-serif; line-height: 1.2; }
h1 { font-size: 20pt; } h2 { font-size: 16pt; } h3 { font-size: 13pt; }
pre, code { font-family: "DejaVu Sans Mono", monospace; font-size: 9.5pt; }
pre { white-space: pre-wrap; border-left: 2pt solid #888; padding-left: 6pt; }
table { border-collapse: collapse; } td, th { border: 0.6pt solid #666; padding: 2pt 4pt; }
img { max-width: 100%; }
blockquote { border-left: 2pt solid #888; margin-left: 0; padding-left: 8pt; color: #333; }
"""

_WIKILINK_EMBED = re.compile(r"!\[\[([^\]|]+)(?:\|[^\]]*)?\]\]")
_WIKILINK = re.compile(r"\[\[([^\]|]+)(?:\|([^\]]*))?\]\]")
# Checkboxes become plain characters (WeasyPrint lays out form inputs as blocks; pandoc
# would turn ☐ ☑ ☒ back into inputs, so □ ▣ it is).
_TASK = re.compile(r"^(\s*[-*+]) \[( |x|X)\] ", re.M)


def obsidian_to_pandoc(markdown: str, vault: Path, note_dir: Path) -> str:
    """Turn Obsidian-only syntax into plain Markdown pandoc understands."""

    def embed(m: re.Match) -> str:
        target = m.group(1).strip()
        for base in (note_dir, vault):
            if (base / target).exists():
                return f"![]({(base / target).resolve()})"
        found = next(vault.rglob(Path(target).name), None)
        return f"![]({found.resolve()})" if found else ""

    markdown = _WIKILINK_EMBED.sub(embed, markdown)
    markdown = _TASK.sub(lambda m: f"{m.group(1)} {'□' if m.group(2) == ' ' else '▣'} ", markdown)
    return _WIKILINK.sub(lambda m: m.group(2) or m.group(1), markdown)


def note_to_pdf(title: str, markdown: str, vault: Path, note_dir: Path, dest: Path) -> Path:
    dest.parent.mkdir(parents=True, exist_ok=True)
    css = dest.with_suffix(".css")
    css.write_text(CSS)
    source = f"# {title}\n\n" + obsidian_to_pandoc(markdown, vault, note_dir)
    subprocess.run(
        ["pandoc", "--from", "markdown", "--pdf-engine", "weasyprint",
         "--css", str(css), "--metadata", f"pagetitle={title}", "-o", str(dest)],
        input=source, text=True, check=True, capture_output=True,
    )
    css.unlink()
    return dest
