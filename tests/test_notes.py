from inkd.notes import BEGIN, END, Note, PageText, block_for_pages, safe_name


def test_parse_and_render_roundtrip():
    text = "---\ntitle: X\nremarkable: true\n---\n# Hello\n\nBody\n"
    note = Note.parse(text)
    assert note.meta == {"title": "X", "remarkable": True}
    assert note.body == "# Hello\n\nBody\n"
    assert Note.parse(note.render()).meta == note.meta


def test_set_block_appends_then_replaces_and_keeps_user_text():
    note = Note({}, "# Meeting\n\nMy own notes.\n")
    note.set_block("first")
    assert note.body.count(BEGIN) == 1 and "first" in note.body
    note.body = note.body.replace("My own notes.", "My edited notes.")
    note.set_block("second")
    assert "first" not in note.body and "second" in note.body
    assert "My edited notes." in note.body
    assert note.body.count(BEGIN) == 1 and note.body.count(END) == 1


def test_user_hash_ignores_inkd_block_and_keys():
    note = Note({"remarkable": True}, "# Plan\n\nText\n")
    before = note.user_hash()
    note.set_block(block_for_pages([PageText(1, "a.png", "handwriting")], heading="Annotations"))
    note.meta["inkd_updated"] = "2026-10-29T10:00:00+00:00"
    assert note.user_hash() == before
    note.body = note.body.replace("Text", "Changed")
    assert note.user_hash() != before


def test_block_for_pages():
    block = block_for_pages([PageText(2, "img/p002.png", "line")])
    assert "### Page 2" in block and "![[img/p002.png]]" in block and "line" in block


def test_safe_name():
    assert safe_name('a/b:c?"d') == "a-b-c--d"
    assert safe_name(" . ") == "Untitled"
