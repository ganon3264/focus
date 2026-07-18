import logging
import os
import sys

DEBUG_MODE = os.environ.get("FOCUS_DEBUG", "0").lower() in ("1", "true", "yes")

LOG_LEVEL = logging.DEBUG if DEBUG_MODE else logging.INFO


class UvicornFormatter(logging.Formatter):
    def format(self, record):
        level_color = {
            logging.DEBUG: "\x1b[36m",  # Cyan
            logging.INFO: "\x1b[32m",  # Green
            logging.WARNING: "\x1b[33m",  # Yellow
            logging.ERROR: "\x1b[31m",  # Red
        }.get(record.levelno, "\x1b[0m")
        reset = "\x1b[0m"

        levelname = f"{level_color}{record.levelname}{reset}:"
        padding = " " * (10 - len(record.levelname) - 1)

        record.msg = f"{record.name}: {record.msg}"
        self._style._fmt = f"{levelname}{padding}%(message)s"
        return super().format(record)


console_handler = logging.StreamHandler(sys.stdout)
console_handler.setFormatter(UvicornFormatter())

root_logger = logging.getLogger("focus")
root_logger.setLevel(LOG_LEVEL)
root_logger.addHandler(console_handler)
root_logger.propagate = False

logging.getLogger("uvicorn.access").setLevel(logging.WARNING)

if DEBUG_MODE:
    root_logger.info("Debug output enabled via FOCUS_DEBUG")


def get_logger(name: str) -> logging.Logger:
    return logging.getLogger(f"focus.{name}")
