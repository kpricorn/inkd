"""Handwriting recognition: page image in, Markdown out."""

from __future__ import annotations

import base64
import logging
from pathlib import Path

from .config import OcrConfig

log = logging.getLogger(__name__)

PROMPT = """This is one page of handwritten notes from a reMarkable tablet.
Transcribe it to Markdown.

- Keep the author's words and language; do not translate, summarise or correct them.
- Use Markdown structure where the page shows it: headings, bullet and numbered lists,
  checkboxes (- [ ] / - [x]), tables.
- Describe drawings and diagrams briefly in italics, e.g. *[diagram: flow from A to B]*.
- Mark words you cannot read as [?].
- Answer with the transcription only, no preamble. If the page is empty, answer with nothing."""


class Recognizer:
    def transcribe(self, image: Path) -> str:
        raise NotImplementedError


class NoRecognizer(Recognizer):
    def transcribe(self, image: Path) -> str:
        return ""


class ClaudeRecognizer(Recognizer):
    def __init__(self, cfg: OcrConfig):
        import anthropic

        self.client = anthropic.Anthropic()
        self.cfg = cfg

    def transcribe(self, image: Path) -> str:
        data = base64.standard_b64encode(image.read_bytes()).decode()
        prompt = PROMPT + (f"\n\n{self.cfg.instructions}" if self.cfg.instructions else "")
        response = self.client.beta.messages.create(
            model=self.cfg.model,
            max_tokens=16000,
            output_config={"effort": self.cfg.effort},
            # On a safety decline, let the API retry on a fallback model.
            betas=["server-side-fallback-2026-07-01"],
            fallbacks="default",
            messages=[{
                "role": "user",
                "content": [
                    {"type": "image", "source": {"type": "base64", "media_type": "image/png", "data": data}},
                    {"type": "text", "text": prompt},
                ],
            }],
        )
        if response.stop_reason == "refusal":
            log.warning("transcription of %s was declined", image)
            return "*[transcription declined]*"
        if response.stop_reason == "max_tokens":
            log.warning("transcription of %s was cut off", image)
        return "".join(b.text for b in response.content if b.type == "text").strip()


def make(cfg: OcrConfig) -> Recognizer:
    if cfg.backend == "claude":
        return ClaudeRecognizer(cfg)
    if cfg.backend == "none":
        return NoRecognizer()
    raise ValueError(f"unknown ocr backend {cfg.backend!r}")
