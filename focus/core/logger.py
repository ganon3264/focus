import logging
import os
import sys

DEBUG_MODE = os.environ.get("FOCUS_DEBUG", "0").lower() in ("1", "true", "yes")

LOG_LEVEL = logging.DEBUG if DEBUG_MODE else logging.INFO


class UvicornFormatter(logging.Formatter):
    def __init__(self, fmt=None, datefmt=None, use_colors=None):
        super().__init__(datefmt=datefmt or "%Y-%m-%d %H:%M:%S")
        # Uvicorn's dictConfig supplies use_colors (None = auto-detect).
        self.use_colors = sys.stdout.isatty() if use_colors is None else use_colors

    def format(self, record):
        reset = "\x1b[0m"
        if self.use_colors:
            level_color = {
                logging.DEBUG: "\x1b[36m",
                logging.INFO: "\x1b[32m",
                logging.WARNING: "\x1b[33m",
                logging.ERROR: "\x1b[31m",
            }.get(record.levelno, reset)
            levelname = f"{level_color}{record.levelname}{reset}:"
        else:
            levelname = f"{record.levelname}:"
        padding = " " * (10 - len(record.levelname) - 1)

        display_name = "uvicorn" if record.name == "uvicorn.error" else record.name
        record.msg = f"{display_name}: {record.msg}"
        self._style._fmt = f"%(asctime)s {levelname}{padding}%(message)s"
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
