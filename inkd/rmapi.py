"""Thin wrapper around the rmapi command line (ddvk fork), pointed at rmfakecloud.

rmapi reads the server from RMAPI_HOST and its token from ~/.config/rmapi/ (or
RMAPI_CONFIG); `inkd login` runs it once interactively to pair it.
"""

from __future__ import annotations

import json
import logging
import subprocess
from dataclasses import dataclass
from pathlib import Path

log = logging.getLogger(__name__)


class RmapiError(RuntimeError):
    pass


@dataclass
class Entry:
    path: str
    is_dir: bool


@dataclass
class Stat:
    doc_id: str
    version: str


def parse_find(output: str) -> list[Entry]:
    """Parse `rmapi find` output: one `[d] /path` or `[f] /path` per line."""
    entries = []
    for line in output.splitlines():
        line = line.strip()
        if len(line) < 4 or line[0] != "[" or line[2] != "]":
            continue
        kind, path = line[1], line[3:].strip()
        if kind in "df" and path:
            entries.append(Entry(path=path if path.startswith("/") else "/" + path, is_dir=kind == "d"))
    return entries


def parse_stat(output: str) -> Stat:
    """Parse `rmapi stat` output, a JSON object describing the entry."""
    start = output.find("{")
    if start < 0:
        raise RmapiError(f"unexpected stat output: {output[:200]!r}")
    data = json.loads(output[start:])
    doc_id = str(data.get("ID") or data.get("Id") or data.get("id") or "")
    # Version alone does not always change on sync 1.5, so combine it with the
    # client modification time.
    version = f"{data.get('Version', '')}@{data.get('ModifiedClient', '')}"
    if not doc_id:
        raise RmapiError(f"stat without ID: {output[:200]!r}")
    return Stat(doc_id=doc_id, version=version)


class Rmapi:
    def __init__(self, binary: str = "rmapi"):
        self.binary = binary

    def _run(self, *args: str, cwd: Path | None = None) -> str:
        # -ni: fail instead of waiting for a pairing code when the token is gone.
        # rmapi reports some command errors on stderr with exit code 0, so callers
        # check the result (a downloaded file, parseable output) rather than trusting it.
        cmd = [self.binary, "-ni", *args]
        log.debug("run %s", cmd)
        proc = subprocess.run(cmd, cwd=cwd, capture_output=True, text=True)
        if proc.returncode != 0:
            raise RmapiError(f"{' '.join(cmd)} failed: {proc.stderr.strip() or proc.stdout.strip()}")
        return proc.stdout

    def find(self, root: str) -> list[Entry]:
        return parse_find(self._run("find", root))

    def stat(self, path: str) -> Stat:
        return parse_stat(self._run("stat", path))

    def download(self, path: str, dest_dir: Path) -> Path:
        """Download a document as .rmdoc (a zip of the document's raw files)."""
        dest_dir.mkdir(parents=True, exist_ok=True)
        before = set(dest_dir.iterdir())
        self._run("get", path, cwd=dest_dir)
        new = [p for p in dest_dir.iterdir() if p not in before and p.suffix in (".rmdoc", ".zip")]
        if not new:
            raise RmapiError(f"get {path}: no .rmdoc written")
        return new[0]

    def mkdir(self, path: str) -> None:
        parts = [p for p in path.split("/") if p]
        for i in range(1, len(parts) + 1):
            self._run("mkdir", "/" + "/".join(parts[:i]))  # prints "entry already exists" if so

    def put(self, file: Path, folder: str) -> None:
        self.mkdir(folder)
        self._run("put", str(file), folder)

    def remove(self, path: str) -> None:
        self._run("rm", path)
