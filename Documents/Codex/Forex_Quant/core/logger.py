from __future__ import annotations

import logging
from pathlib import Path


def setup_logging(log_path: str | Path = "data/live_logs/quanta.log") -> logging.Logger:
    path = Path(log_path)
    path.parent.mkdir(parents=True, exist_ok=True)

    logger = logging.getLogger("quanta")
    logger.setLevel(logging.INFO)
    logger.handlers.clear()

    formatter = logging.Formatter("%(asctime)s %(levelname)s %(name)s %(message)s")

    console = logging.StreamHandler()
    console.setFormatter(formatter)
    logger.addHandler(console)

    file_handler = logging.FileHandler(path, encoding="utf-8")
    file_handler.setFormatter(formatter)
    logger.addHandler(file_handler)

    return logger

