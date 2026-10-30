"""Structured logging utility with safe cross-platform encoding."""

import logging
import sys


class SafeConsoleHandler(logging.StreamHandler):
    """Console handler that safely formats strings on Windows consoles with limited encodings."""

    def emit(self, record):
        try:
            msg = self.format(record)
            stream = self.stream
            stream.write(msg + self.terminator)
            self.flush()
        except UnicodeEncodeError:
            try:
                # Replace unprintable characters gracefully
                safe_msg = msg.encode(sys.stdout.encoding or "ascii", errors="replace").decode(
                    sys.stdout.encoding or "ascii"
                )
                self.stream.write(safe_msg + self.terminator)
                self.flush()
            except Exception:
                self.handleError(record)
        except Exception:
            self.handleError(record)


def get_logger(name: str = "mixsmith") -> logging.Logger:
    """Configures and returns a structured logger."""
    logger = logging.getLogger(name)
    if not logger.handlers:
        logger.setLevel(logging.INFO)
        handler = SafeConsoleHandler(sys.stdout)
        formatter = logging.Formatter(
            fmt="[%(levelname)s] %(message)s",
            datefmt="%Y-%m-%d %H:%M:%S"
        )
        handler.setFormatter(formatter)
        logger.addHandler(handler)
        logger.propagate = False
    return logger
