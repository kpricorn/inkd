"""Configuration, read from a TOML file (see config.example.toml)."""

from __future__ import annotations

import tomllib
from dataclasses import dataclass, field, fields
from pathlib import Path


@dataclass
class RemarkableConfig:
    rmapi: str = "rmapi"
    # Tablet folder to export; everything below it is synced.
    root: str = "/"
    exclude: list[str] = field(default_factory=lambda: ["/trash"])
    # Tablet folder that receives files from the cloud inbox.
    inbox_folder: str = "/Inbox"
    # Tablet folder that receives notes published from Obsidian.
    obsidian_folder: str = "/Obsidian"


@dataclass
class StorageConfig:
    # rclone remote that receives the rendered PDFs, e.g. "dropbox:reMarkable"
    # or "gdrive:reMarkable". Empty disables the export.
    remote: str = ""
    # rclone remote watched for PDF/EPUB files to send to the tablet. Empty disables it.
    inbox: str = ""
    rclone: str = "rclone"


@dataclass
class ObsidianConfig:
    # Path of the vault on disk. Empty disables everything Obsidian-related.
    vault: str = ""
    # Folder in the vault for notes made from tablet notebooks.
    notes_dir: str = "reMarkable"
    # Folder in the vault for page images.
    attachments_dir: str = "reMarkable/_pages"
    # Frontmatter key that marks a note to be published to the tablet.
    publish_key: str = "remarkable"


@dataclass
class OcrConfig:
    # "claude" or "none"
    backend: str = "claude"
    model: str = "claude-opus-5-5"
    effort: str = "medium"
    # Extra instructions appended to the transcription prompt (languages, conventions).
    instructions: str = ""


@dataclass
class SyncConfig:
    interval: int = 300
    data_dir: str = "/data"


@dataclass
class Config:
    remarkable: RemarkableConfig = field(default_factory=RemarkableConfig)
    storage: StorageConfig = field(default_factory=StorageConfig)
    obsidian: ObsidianConfig = field(default_factory=ObsidianConfig)
    ocr: OcrConfig = field(default_factory=OcrConfig)
    sync: SyncConfig = field(default_factory=SyncConfig)

    @property
    def data_dir(self) -> Path:
        return Path(self.sync.data_dir)


def _section(cls, values: dict):
    known = {f.name for f in fields(cls)}
    unknown = set(values) - known
    if unknown:
        raise ValueError(f"unknown {cls.__name__} keys: {', '.join(sorted(unknown))}")
    return cls(**values)


def load(path: str | Path) -> Config:
    with open(path, "rb") as f:
        raw = tomllib.load(f)
    sections = {f.name: f.type for f in fields(Config)}
    unknown = set(raw) - set(sections)
    if unknown:
        raise ValueError(f"unknown config sections: {', '.join(sorted(unknown))}")
    return Config(
        remarkable=_section(RemarkableConfig, raw.get("remarkable", {})),
        storage=_section(StorageConfig, raw.get("storage", {})),
        obsidian=_section(ObsidianConfig, raw.get("obsidian", {})),
        ocr=_section(OcrConfig, raw.get("ocr", {})),
        sync=_section(SyncConfig, raw.get("sync", {})),
    )
