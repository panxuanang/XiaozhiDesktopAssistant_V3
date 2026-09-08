from __future__ import annotations

import logging
from logging.handlers import RotatingFileHandler

from .paths import logs_dir


def setup_logging() -> None:
    root = logging.getLogger()
    if root.handlers:
        return
    root.setLevel(logging.INFO)
    fmt = logging.Formatter("%(asctime)s %(levelname)s %(name)s - %(message)s")
    fh = RotatingFileHandler(logs_dir() / "assistant.log", maxBytes=4_000_000, backupCount=5, encoding="utf-8")
    fh.setFormatter(fmt)
    root.addHandler(fh)
    sh = logging.StreamHandler()
    sh.setFormatter(fmt)
    root.addHandler(sh)
