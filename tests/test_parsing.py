import pytest

from inkd import config
from inkd.rmapi import RmapiError, parse_find, parse_stat
from inkd.storage import join


def test_parse_find():
    out = "[d] /Notes\n[f] /Notes/Meeting 1\nnoise\n[f] Book.pdf\n"
    entries = parse_find(out)
    assert [(e.path, e.is_dir) for e in entries] == [
        ("/Notes", True), ("/Notes/Meeting 1", False), ("/Book.pdf", False)]


def test_parse_stat():
    s = parse_stat('{"ID": "abc", "Version": 3, "ModifiedClient": "2026-10-29T10:00:00Z"}')
    assert s.doc_id == "abc" and s.version == "3@2026-10-29T10:00:00Z"
    with pytest.raises(RmapiError):
        parse_stat("not json")


def test_join():
    assert join("dropbox:", "/a/b") == "dropbox:a/b"
    assert join("dropbox:reMarkable", "/Notes/x.pdf") == "dropbox:reMarkable/Notes/x.pdf"
    assert join("gdrive:rm/", "x") == "gdrive:rm/x"


def test_example_config_loads():
    cfg = config.load("config.example.toml")
    assert cfg.ocr.model == "claude-opus-5-5"


def test_unknown_key_is_rejected(tmp_path):
    p = tmp_path / "c.toml"
    p.write_text("[ocr]\nmodle = 'x'\n")
    with pytest.raises(ValueError, match="modle"):
        config.load(p)
