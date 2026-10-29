"""Command line: inkd sync | watch | status | login."""

from __future__ import annotations

import argparse
import logging
import os
import sys
import time

from . import config as config_mod
from . import ocr
from .rmapi import Rmapi
from .state import State
from .storage import Rclone
from .sync import Syncer, clean_work


def _syncer(cfg) -> tuple[Syncer, State]:
    state = State(cfg.data_dir / "state.db")
    return Syncer(cfg, state, Rmapi(cfg.remarkable.rmapi), Rclone(cfg.storage.rclone), ocr.make(cfg.ocr)), state


def main(argv: list[str] | None = None) -> None:
    parser = argparse.ArgumentParser(prog="inkd", description=__doc__)
    parser.add_argument("-c", "--config", default=os.environ.get("INKD_CONFIG", "/config/inkd.toml"))
    parser.add_argument("-v", "--verbose", action="store_true")
    sub = parser.add_subparsers(dest="command", required=True)
    sub.add_parser("sync", help="run one sync cycle")
    sub.add_parser("watch", help="run sync cycles forever, every sync.interval seconds")
    sub.add_parser("status", help="list the documents inkd knows about")
    sub.add_parser("login", help="pair rmapi with the server (asks for a one-time code)")
    args = parser.parse_args(argv)

    logging.basicConfig(
        level=logging.DEBUG if args.verbose else logging.INFO,
        format="%(asctime)s %(levelname)s %(name)s: %(message)s",
    )
    cfg = config_mod.load(args.config)

    if args.command == "login":
        os.execvp(cfg.remarkable.rmapi, [cfg.remarkable.rmapi, "ls", "/"])

    syncer, state = _syncer(cfg)
    try:
        if args.command == "sync":
            syncer.cycle()
        elif args.command == "watch":
            while True:
                syncer.cycle()
                clean_work(cfg)
                time.sleep(cfg.sync.interval)
        elif args.command == "status":
            for row in state.documents():
                print(f"{row['origin']:8} {'ink' if row['has_ink'] else '   '} "
                      f"{row['tablet_path']}  ->  {row['note_path'] or '-'}")
    except KeyboardInterrupt:
        sys.exit(130)
    finally:
        state.close()
