"""Centralised logger - file + console handlers."""
import logging
import os
from datetime import datetime


def setup_logger(name: str = "bot3") -> logging.Logger:
    """Return a configured logger with file and console handlers."""
    logger = logging.getLogger(name)
    if logger.handlers:
        return logger

    logger.setLevel(logging.DEBUG)

    fmt = logging.Formatter("%(asctime)s [%(levelname)s] %(name)s: %(message)s")

    ch = logging.StreamHandler()
    ch.setLevel(logging.INFO)
    ch.setFormatter(fmt)
    logger.addHandler(ch)

    os.makedirs("logs", exist_ok=True)
    log_file = f"logs/bot3_{datetime.utcnow().strftime('%Y%m%d')}.log"
    fh = logging.FileHandler(log_file, encoding="utf-8")
    fh.setLevel(logging.DEBUG)
    fh.setFormatter(fmt)
    logger.addHandler(fh)

    return logger
