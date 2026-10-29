import io
import json
import zipfile
from pathlib import Path

import pytest
from rmscene import simple_text_document, write_blocks


def make_rm(text: str) -> bytes:
    buf = io.BytesIO()
    write_blocks(buf, simple_text_document(text))
    return buf.getvalue()


def make_rmdoc(path: Path, doc_id: str, name: str, pages: dict[str, bytes | None]) -> Path:
    content = {"fileType": "notebook", "cPages": {"pages": [{"id": pid} for pid in pages]}}
    with zipfile.ZipFile(path, "w") as z:
        z.writestr(f"{doc_id}.content", json.dumps(content))
        z.writestr(f"{doc_id}.metadata", json.dumps({"visibleName": name}))
        for pid, rm in pages.items():
            if rm is not None:
                z.writestr(f"{doc_id}/{pid}.rm", rm)
    return path


@pytest.fixture
def rm_text():
    return make_rm
