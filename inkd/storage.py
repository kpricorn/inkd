"""Dropbox / Google Drive (or any other rclone remote) through the rclone CLI."""

from __future__ import annotations

import json
import logging
import subprocess
from dataclasses import dataclass
from pathlib import Path

log = logging.getLogger(__name__)


class RcloneError(RuntimeError):
    pass


@dataclass
class RemoteFile:
    name: str
    size: int
    modified: str


class Rclone:
    def __init__(self, binary: str = "rclone"):
        self.binary = binary

    def _run(self, *args: str) -> str:
        cmd = [self.binary, *args]
        log.debug("run %s", cmd)
        proc = subprocess.run(cmd, capture_output=True, text=True)
        if proc.returncode != 0:
            raise RcloneError(f"{' '.join(cmd)} failed: {proc.stderr.strip()}")
        return proc.stdout

    def upload(self, local: Path, remote_path: str) -> None:
        self._run("copyto", str(local), remote_path)

    def download(self, remote_path: str, local: Path) -> None:
        local.parent.mkdir(parents=True, exist_ok=True)
        self._run("copyto", remote_path, str(local))

    def move(self, src: str, dst: str) -> None:
        self._run("moveto", src, dst)

    def list_files(self, remote_dir: str) -> list[RemoteFile]:
        """Files directly in remote_dir (not recursive)."""
        try:
            items = json.loads(self._run("lsjson", "--files-only", remote_dir))
        except RcloneError as e:
            if "directory not found" in str(e):
                return []
            raise
        return [RemoteFile(i["Name"], int(i.get("Size", 0)), i.get("ModTime", "")) for i in items]


def join(remote: str, *parts: str) -> str:
    """Join an rclone remote ("dropbox:reMarkable") with path parts."""
    rest = "/".join(p.strip("/") for p in parts if p.strip("/"))
    if not rest:
        return remote
    return remote + ("" if remote.endswith((":", "/")) else "/") + rest
