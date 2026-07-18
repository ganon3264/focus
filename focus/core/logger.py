import logging
import os
import sys

# Define the log level based on the environment variable
DEBUG_MODE = os.environ.get("FOCUS_DEBUG", "0") in ("1", "true", "True", "yes")

LOG_LEVEL = logging.DEBUG if DEBUG_MODE else logging.INFO


# Set up the formatter
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


# Set up the console handler
console_handler = logging.StreamHandler(sys.stdout)
console_handler.setFormatter(UvicornFormatter())

# Configure the root logger
root_logger = logging.getLogger("focus")
root_logger.setLevel(LOG_LEVEL)
root_logger.addHandler(console_handler)
# Prevent duplicate logs if uvicorn or others try to hijack it
root_logger.propagate = False

# Silence uvicorn's built-in access logging (we handle it ourselves)
logging.getLogger("uvicorn.access").setLevel(logging.WARNING)

if DEBUG_MODE:
    root_logger.info("Debug output enabled via FOCUS_DEBUG")


def get_logger(name: str) -> logging.Logger:
    """Returns a logger for the given module name."""
    return logging.getLogger(f"focus.{name}")
