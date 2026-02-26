"""
Centralised logging setup for the Citrix AI Vision Agent.
Call get_logger(__name__) in every module.
"""

import logging
import sys

import config


def get_logger(name: str) -> logging.Logger:
    """
    Return a module-level logger wired to both console and file.

    Args:
        name: Typically __name__ of the calling module.

    Returns:
        Configured Logger instance.
    """
    logger = logging.getLogger(name)

    if logger.handlers:
        return logger  # Already configured for this name

    logger.setLevel(getattr(logging, config.LOG_LEVEL, logging.DEBUG))

    fmt = logging.Formatter(
        "%(asctime)s | %(levelname)-8s | %(name)s | %(message)s",
        datefmt="%Y-%m-%d %H:%M:%S",
    )

    ch = logging.StreamHandler(sys.stdout)
    ch.setFormatter(fmt)
    logger.addHandler(ch)

    fh = logging.FileHandler(config.LOG_FILE, encoding="utf-8")
    fh.setFormatter(fmt)
    logger.addHandler(fh)

    logger.propagate = False
    return logger
