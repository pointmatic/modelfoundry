# Copyright (c) 2026 Pointmatic
# SPDX-License-Identifier: Apache-2.0
"""JSON line-formatted operational logging for ModelFoundry.

The operator channel (per `tech-spec.md` § Logging and User Output): one JSON
object per line on a caller-supplied target. `rich`-based user-facing output is
handled separately per CLI verb.

`get_logger(name)` returns a logger under the `modelfoundry` namespace and
idempotently attaches a `NullHandler` (library safety) plus a `JsonFormatter`
handler. Importing this module alone adds no handlers anywhere; the root logger
is never configured or hijacked.
"""

from __future__ import annotations

import json
import logging
import sys
from datetime import UTC, datetime
from pathlib import Path
from typing import IO, Any, Final

_PACKAGE: Final = "modelfoundry"

# `LogRecord` standard attributes — anything *not* in this set on
# `record.__dict__` was placed there by a caller via `extra=...`.
_RECORD_RESERVED: Final[frozenset[str]] = frozenset(
    {
        "args",
        "asctime",
        "created",
        "exc_info",
        "exc_text",
        "filename",
        "funcName",
        "levelname",
        "levelno",
        "lineno",
        "message",
        "module",
        "msecs",
        "msg",
        "name",
        "pathname",
        "process",
        "processName",
        "relativeCreated",
        "stack_info",
        "taskName",
        "thread",
        "threadName",
    }
)

# Keys the formatter writes itself; caller `extra=` fields never overwrite them.
_PAYLOAD_KEYS: Final[frozenset[str]] = frozenset(
    {"timestamp", "level", "logger", "message", "exc_info"}
)


class JsonFormatter(logging.Formatter):
    """Format each `LogRecord` as a single-line JSON object.

    Always emits `timestamp` (UTC ISO 8601, `Z` suffix), `level`, `logger`, and
    `message`. Caller `extra=` fields are merged at the top level, skipping any
    key that would shadow a formatter-owned field.
    """

    def format(self, record: logging.LogRecord) -> str:
        timestamp = (
            datetime.fromtimestamp(record.created, UTC).isoformat().replace("+00:00", "Z")
        )
        payload: dict[str, Any] = {
            "timestamp": timestamp,
            "level": record.levelname,
            "logger": record.name,
            "message": record.getMessage(),
        }
        for key, value in record.__dict__.items():
            if key not in _RECORD_RESERVED and key not in _PAYLOAD_KEYS:
                payload[key] = value
        if record.exc_info:
            payload["exc_info"] = self.formatException(record.exc_info)
        return json.dumps(payload, ensure_ascii=False, default=str)


def _make_handler(target: str | Path | IO[str] | None) -> logging.Handler:
    """Build a `JsonFormatter` handler for the resolved target.

    `None` / `"stderr"` → `sys.stderr`; `"stdout"` → `sys.stdout`; any other
    `str`/`Path` → a `FileHandler` at that path; a writable text stream → a
    `StreamHandler` on that stream.
    """
    if target is None or target == "stderr":
        handler: logging.Handler = logging.StreamHandler(sys.stderr)
    elif target == "stdout":
        handler = logging.StreamHandler(sys.stdout)
    elif isinstance(target, (str, Path)):
        handler = logging.FileHandler(Path(target), encoding="utf-8")
    else:
        handler = logging.StreamHandler(target)
    handler.setFormatter(JsonFormatter())
    return handler


def _json_handlers(logger: logging.Logger) -> list[logging.Handler]:
    return [h for h in logger.handlers if isinstance(h.formatter, JsonFormatter)]


def get_logger(
    name: str = _PACKAGE,
    *,
    target: str | Path | IO[str] | None = None,
    level: int | str | None = None,
) -> logging.Logger:
    """Return a logger under the `modelfoundry` namespace.

    Idempotently attaches a `NullHandler` (library safety) and a single
    `JsonFormatter` handler to the package logger. Passing `target` (re)points
    the JSON channel — any existing JSON handler is replaced so a caller can
    redirect output to a file or stream. With no `target`, a default
    `sys.stderr` handler is attached only if none exists yet. The root logger is
    never touched.
    """
    package_logger = logging.getLogger(_PACKAGE)

    if not any(isinstance(h, logging.NullHandler) for h in package_logger.handlers):
        package_logger.addHandler(logging.NullHandler())

    if target is not None:
        for handler in _json_handlers(package_logger):
            package_logger.removeHandler(handler)
            handler.close()
        package_logger.addHandler(_make_handler(target))
    elif not _json_handlers(package_logger):
        package_logger.addHandler(_make_handler(None))

    if level is not None:
        package_logger.setLevel(level)
    elif package_logger.level == logging.NOTSET:
        package_logger.setLevel(logging.INFO)

    qualified = (
        name
        if name == _PACKAGE or name.startswith(f"{_PACKAGE}.")
        else f"{_PACKAGE}.{name}"
    )
    return logging.getLogger(qualified)
