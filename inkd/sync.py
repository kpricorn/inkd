"""One sync cycle: tablet → cloud/Obsidian, cloud inbox → tablet, Obsidian → tablet."""

from __future__ import annotations

import logging
import shutil
import tempfile
from datetime import datetime, timezone
from pathlib import Path, PurePosixPath

from . import notes, publish, rmdoc
from .config import Config
from .ocr import Recognizer
from .rmapi import Rmapi
from .state import State
from .storage import Rclone, join

log = logging.getLogger(__name__)

SEND_TYPES = {".pdf", ".epub"}
SKIP_VAULT_DIRS = {".obsidian", ".trash", ".git"}


class Syncer:
    def __init__(self, cfg: Config, state: State, rm: Rmapi, rclone: Rclone, recognizer: Recognizer):
        self.cfg, self.state, self.rm, self.rclone, self.ocr = cfg, state, rm, rclone, recognizer
        self.vault = Path(cfg.obsidian.vault) if cfg.obsidian.vault else None
        remote, inbox = cfg.storage.remote.rstrip("/"), cfg.storage.inbox.rstrip("/")
        if remote and inbox and (inbox == remote or inbox.startswith(remote + "/")):
            raise ValueError("storage.inbox must not be inside storage.remote (files would loop)")

    def cycle(self) -> None:
        for step in (self.pull_tablet, self.push_inbox, self.publish_notes):
            try:
                step()
            except Exception:
                log.exception("%s failed", step.__name__)

    # tablet → cloud and Obsidian

    def _excluded(self, path: str) -> bool:
        lower = path.lower()
        return any(lower == e.lower() or lower.startswith(e.lower().rstrip("/") + "/")
                   for e in self.cfg.remarkable.exclude)

    def pull_tablet(self) -> None:
        for entry in self.rm.find(self.cfg.remarkable.root):
            if entry.is_dir or self._excluded(entry.path):
                continue
            try:
                stat = self.rm.stat(entry.path)
                prev = self.state.document(stat.doc_id)
                if prev and prev["version"] == stat.version and prev["tablet_path"] == entry.path:
                    continue
                self.export(entry.path, stat.doc_id, stat.version)
            except Exception:
                log.exception("export of %s failed", entry.path)

    def export(self, tablet_path: str, doc_id: str, version: str) -> None:
        log.info("exporting %s", tablet_path)
        prev = self.state.document(doc_id)
        origin = prev["origin"] if prev else "tablet"
        with tempfile.TemporaryDirectory(dir=self._work()) as tmp:
            doc = rmdoc.load(self.rm.download(tablet_path, Path(tmp)))
            written = [p for p in doc.pages if rmdoc.has_ink(p) or rmdoc.typed_text(p)]
            has_ink = any(rmdoc.has_ink(p) for p in written)

            if self.cfg.storage.remote:
                self._upload(doc, tablet_path, written, Path(tmp))

            note_path = prev["note_path"] if prev else None
            if self.vault and written:
                note_path = self._write_note(doc, tablet_path, origin, note_path, written)

        self.state.save_document(doc_id, tablet_path, version, note_path, origin, has_ink)

    def _upload(self, doc: rmdoc.RmDoc, tablet_path: str, written, tmp: Path) -> None:
        remote = self.cfg.storage.remote
        if doc.original is not None and doc.file_type in ("pdf", "epub"):
            original = tmp / f"original.{doc.file_type}"
            original.write_bytes(doc.original)
            self.rclone.upload(original, join(remote, f"{tablet_path}.{doc.file_type}"))
            if written:
                ink = rmdoc.render_pdf(doc, tmp / "ink.pdf")
                self.rclone.upload(ink, join(remote, f"{tablet_path} (ink).pdf"))
        elif written:
            self.rclone.upload(rmdoc.render_pdf(doc, tmp / "ink.pdf"), join(remote, f"{tablet_path}.pdf"))

    def _write_note(self, doc, tablet_path, origin, note_path, written) -> str:
        o = self.cfg.obsidian
        if not note_path:
            parts = [notes.safe_name(p) for p in PurePosixPath(tablet_path).parts if p != "/"]
            note_path = str(PurePosixPath(o.notes_dir, *parts).with_suffix(".md"))
        path = self.vault / note_path
        note = notes.Note.read(path)
        if origin == "obsidian" and not path.exists():
            log.warning("note %s for %s no longer exists; not recreating it", note_path, tablet_path)
            return note_path

        pages = []
        for page in written:
            image = PurePosixPath(o.attachments_dir, doc.doc_id, f"p{page.index + 1:03}.png")
            rmdoc.render_png(page, self.vault / image)
            text = self.state.page_text(doc.doc_id, page.page_id, page.rm_hash)
            if text is None:
                text = rmdoc.typed_text(page)
                if rmdoc.has_ink(page):
                    text = (text + "\n\n" if text else "") + self.ocr.transcribe(self.vault / image)
                self.state.save_page(doc.doc_id, page.page_id, page.rm_hash, text)
            pages.append(notes.PageText(page.index + 1, str(image), text))

        if origin == "obsidian":
            block = notes.block_for_pages(pages, heading="Handwritten on the reMarkable")
        else:
            block = notes.block_for_pages(pages)
            if not note.body.strip():
                note.body = f"# {doc.name}\n"
            note.meta.update({"inkd_id": doc.doc_id, "inkd_source": tablet_path})
        note.meta["inkd_updated"] = datetime.now(timezone.utc).isoformat(timespec="seconds")
        note.set_block(block)
        note.write(path)
        return note_path

    # cloud inbox → tablet

    def push_inbox(self) -> None:
        inbox = self.cfg.storage.inbox
        if not inbox:
            return
        for f in self.rclone.list_files(inbox):
            if Path(f.name).suffix.lower() not in SEND_TYPES or self.state.inbox_seen(f.name, f.size, f.modified):
                continue
            log.info("sending %s to the tablet", f.name)
            with tempfile.TemporaryDirectory(dir=self._work()) as tmp:
                local = Path(tmp) / f.name
                self.rclone.download(join(inbox, f.name), local)
                self.rm.put(local, self.cfg.remarkable.inbox_folder)
            self.rclone.move(join(inbox, f.name), join(inbox, "sent", f.name))
            self.state.save_inbox(f.name, f.size, f.modified)

    # Obsidian → tablet

    def publish_notes(self) -> None:
        if not self.vault:
            return
        key = self.cfg.obsidian.publish_key
        for md in sorted(self.vault.rglob("*.md")):
            rel = md.relative_to(self.vault)
            if SKIP_VAULT_DIRS & set(rel.parts):
                continue
            note = notes.Note.read(md)
            # Notes made from tablet notebooks are never sent back.
            if note.meta.get(key) is not True or "inkd_id" in note.meta:
                continue
            content_hash = note.user_hash()
            prev = self.state.published(rel.as_posix())
            if prev and prev["content_hash"] == content_hash:
                continue
            try:
                self._publish(md, rel, note, content_hash, prev)
            except Exception:
                log.exception("publishing %s failed", rel)

    def _publish(self, md: Path, rel: Path, note: notes.Note, content_hash: str, prev) -> None:
        folder = str(PurePosixPath(self.cfg.remarkable.obsidian_folder, *rel.parent.parts))
        name = notes.safe_name(md.stem)
        if prev:
            old = self.state.document_at(prev["tablet_path"])
            if old and old["has_ink"]:
                # Never overwrite handwriting: the new version goes next to the old one.
                name = f"{name} ({datetime.now().strftime('%Y-%m-%d %H%M')})"
            else:
                try:
                    self.rm.remove(prev["tablet_path"])
                except Exception:
                    log.warning("could not remove %s before republishing", prev["tablet_path"])
        log.info("publishing %s to %s/%s", rel, folder, name)
        with tempfile.TemporaryDirectory(dir=self._work()) as tmp:
            pdf = publish.note_to_pdf(md.stem, note.user_body(), self.vault, md.parent, Path(tmp) / f"{name}.pdf")
            self.rm.put(pdf, folder)
        tablet_path = f"{folder.rstrip('/')}/{name}"
        stat = self.rm.stat(tablet_path)
        self.state.save_document(stat.doc_id, tablet_path, stat.version, rel.as_posix(), "obsidian")
        self.state.save_published(rel.as_posix(), content_hash, tablet_path)

    def _work(self) -> Path:
        work = self.cfg.data_dir / "work"
        work.mkdir(parents=True, exist_ok=True)
        return work


def clean_work(cfg: Config) -> None:
    shutil.rmtree(cfg.data_dir / "work", ignore_errors=True)
