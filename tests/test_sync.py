from pathlib import Path

import pytest

from inkd.config import Config
from inkd.notes import Note
from inkd.ocr import NoRecognizer
from inkd.rmapi import Entry, Stat
from inkd.state import State
from inkd.sync import Syncer

from .conftest import make_rm, make_rmdoc


class FakeRmapi:
    def __init__(self, tmp: Path):
        self.tmp = tmp
        self.docs = {}  # path -> (doc_id, version, pages)
        self.put_calls = []
        self.removed = []

    def find(self, root):
        return [Entry(p, False) for p in self.docs]

    def stat(self, path):
        doc_id, version, _ = self.docs[path]
        return Stat(doc_id, version)

    def download(self, path, dest):
        doc_id, _, pages = self.docs[path]
        return make_rmdoc(dest / f"{doc_id}.rmdoc", doc_id, Path(path).name, pages)

    def put(self, file, folder):
        self.put_calls.append((file.name, folder, file.read_bytes()[:4]))
        self.docs[f"{folder}/{file.stem}"] = (f"pub-{len(self.put_calls)}", "1@t", {})

    def remove(self, path):
        self.removed.append(path)
        self.docs.pop(path, None)


class FakeRclone:
    def __init__(self):
        self.uploads = []

    def upload(self, local, remote):
        self.uploads.append(remote)


@pytest.fixture
def env(tmp_path):
    cfg = Config()
    cfg.sync.data_dir = str(tmp_path / "data")
    cfg.obsidian.vault = str(tmp_path / "vault")
    cfg.storage.remote = "dropbox:reMarkable/Tablet"
    (tmp_path / "vault").mkdir()
    rm, rclone = FakeRmapi(tmp_path), FakeRclone()
    state = State(tmp_path / "data" / "state.db")
    return Syncer(cfg, state, rm, rclone, NoRecognizer()), rm, rclone, tmp_path / "vault"


def test_notebook_becomes_note_and_pdf(env):
    syncer, rm, rclone, vault = env
    rm.docs["/Work/Meeting"] = ("d1", "1@a", {"p1": make_rm("Agenda item"), "p2": None})
    syncer.pull_tablet()

    note_file = vault / "reMarkable/Work/Meeting.md"
    note = Note.read(note_file)
    assert note.meta["inkd_id"] == "d1" and note.meta["inkd_source"] == "/Work/Meeting"
    assert "Agenda item" in note.body and "### Page 1" in note.body and "Page 2" not in note.body
    assert (vault / "reMarkable/_pages/d1/p001.png").exists()
    assert rclone.uploads == ["dropbox:reMarkable/Tablet/Work/Meeting.pdf"]

    # Unchanged version: nothing happens; user text added to the note survives a re-export.
    syncer.pull_tablet()
    assert len(rclone.uploads) == 1
    note_file.write_text(note_file.read_text().replace("# Meeting", "# Meeting\n\nMy thoughts"))
    rm.docs["/Work/Meeting"] = ("d1", "2@b", {"p1": make_rm("Agenda item two"), "p2": None})
    syncer.pull_tablet()
    body = Note.read(note_file).body
    assert "My thoughts" in body and "Agenda item two" in body and body.count("inkd:begin") == 1


def test_publish_note_and_annotations_come_back(env, monkeypatch):
    syncer, rm, rclone, vault = env
    monkeypatch.setattr("inkd.publish.note_to_pdf", lambda title, md, v, d, dest: (dest.write_bytes(b"%PDF"), dest)[1])
    (vault / "Projects").mkdir()
    src = vault / "Projects/Plan.md"
    src.write_text("---\nremarkable: true\n---\n# Plan\n\nStep one\n")
    (vault / "Other.md").write_text("# not published\n")

    syncer.publish_notes()
    assert rm.put_calls == [("Plan.pdf", "/Obsidian/Projects", b"%PDF")]
    syncer.publish_notes()  # unchanged: not published again
    assert len(rm.put_calls) == 1

    # The user writes on the published document; the text lands in the source note.
    rm.docs["/Obsidian/Projects/Plan"] = ("pub-1", "2@x", {"p1": make_rm("margin note")})
    syncer.pull_tablet()
    note = Note.read(src)
    assert "Handwritten on the reMarkable" in note.body and "margin note" in note.body
    assert "Step one" in note.body
    assert not (vault / "reMarkable/Obsidian/Projects/Plan.md").exists()

    # Writing the annotations does not count as an edit, so nothing is republished.
    syncer.publish_notes()
    assert len(rm.put_calls) == 1

    # A real edit is republished; the old version had no ink, so it is replaced.
    src.write_text(src.read_text().replace("Step one", "Step one and two"))
    syncer.publish_notes()
    assert len(rm.put_calls) == 2 and rm.removed == ["/Obsidian/Projects/Plan"]


def test_inbox_inside_export_is_rejected(env):
    syncer, *_ = env
    syncer.cfg.storage.inbox = "dropbox:reMarkable/Tablet/In"
    with pytest.raises(ValueError):
        Syncer(syncer.cfg, syncer.state, syncer.rm, syncer.rclone, syncer.ocr)
