"""Read a downloaded .rmdoc and render its pages.

An .rmdoc is a zip of the document's raw files:
  <id>.content        JSON, page order (cPages.pages on firmware 3.x, pages before)
  <id>.metadata       JSON, name and parent
  <id>/<page id>.rm   strokes and typed text of one page (format v6)
  <id>.pdf / .epub    the original file, for imported documents
"""

from __future__ import annotations

import hashlib
import io
import json
import zipfile
from dataclasses import dataclass
from pathlib import Path

import cairosvg
from pypdf import PdfReader, PdfWriter
from rmc.exporters.markdown import print_text
from rmc.exporters.svg import tree_to_svg
from rmscene import read_tree
from rmscene import scene_items as si


@dataclass
class Page:
    page_id: str
    index: int  # 0-based position in the document
    rm: bytes | None  # None: the page has never been written on

    @property
    def rm_hash(self) -> str:
        return hashlib.sha256(self.rm or b"").hexdigest()


@dataclass
class RmDoc:
    doc_id: str
    name: str
    file_type: str  # "notebook", "pdf" or "epub"
    pages: list[Page]
    original: bytes | None  # the imported PDF/EPUB, if any


def page_ids(content: dict) -> list[str]:
    cpages = content.get("cPages")
    if cpages and cpages.get("pages"):
        return [p["id"] for p in cpages["pages"] if not p.get("deleted")]
    return list(content.get("pages") or [])


def load(path: Path) -> RmDoc:
    with zipfile.ZipFile(path) as z:
        names = z.namelist()
        content_name = next(n for n in names if n.endswith(".content"))
        doc_id = content_name[: -len(".content")]
        content = json.loads(z.read(content_name))
        metadata = {}
        if f"{doc_id}.metadata" in names:
            metadata = json.loads(z.read(f"{doc_id}.metadata"))
        file_type = content.get("fileType") or "notebook"
        original = None
        for ext in ("pdf", "epub"):
            if f"{doc_id}.{ext}" in names:
                original = z.read(f"{doc_id}.{ext}")
        pages = []
        for i, pid in enumerate(page_ids(content)):
            rm_name = f"{doc_id}/{pid}.rm"
            pages.append(Page(pid, i, z.read(rm_name) if rm_name in names else None))
    return RmDoc(
        doc_id=doc_id,
        name=metadata.get("visibleName", doc_id),
        file_type=file_type,
        pages=pages,
        original=original,
    )


def has_ink(page: Page) -> bool:
    if not page.rm:
        return False
    tree = read_tree(io.BytesIO(page.rm))
    return any(isinstance(item, si.Line) for item in tree.walk())


def typed_text(page: Page) -> str:
    """Text typed on the tablet (keyboard), which needs no recognition."""
    if not page.rm:
        return ""
    out = io.StringIO()
    print_text(io.BytesIO(page.rm), out)
    text = out.getvalue()
    # rmc appends highlighted PDF text under "# Highlights"; drop the heading when empty.
    head, _, highlights = text.partition("\n\n# Highlights")
    highlights = highlights.strip()
    return head.strip() + (f"\n\nHighlights:\n{highlights}" if highlights else "")


def page_svg(page: Page) -> str:
    out = io.StringIO()
    tree_to_svg(read_tree(io.BytesIO(page.rm or b"")), out)
    return out.getvalue()


def render_png(page: Page, dest: Path, width: int = 1404) -> Path:
    """Render a page's ink (strokes and typed text) to PNG on white."""
    dest.parent.mkdir(parents=True, exist_ok=True)
    cairosvg.svg2png(
        bytestring=page_svg(page).encode(), write_to=str(dest),
        output_width=width, background_color="white",
    )
    return dest


def render_pdf(doc: RmDoc, dest: Path) -> Path:
    """Render the document's ink to a PDF, one page per written page.

    For imported PDFs this is the ink only; the original travels next to it.
    """
    writer = PdfWriter()
    for page in doc.pages:
        if not has_ink(page) and not typed_text(page):
            continue
        pdf = cairosvg.svg2pdf(bytestring=page_svg(page).encode(), background_color="white")
        writer.append(PdfReader(io.BytesIO(pdf)))
    dest.parent.mkdir(parents=True, exist_ok=True)
    with open(dest, "wb") as f:
        writer.write(f)
    return dest
