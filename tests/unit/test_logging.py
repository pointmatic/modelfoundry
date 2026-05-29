# Copyright (c) 2026 Pointmatic
# SPDX-License-Identifier: Apache-2.0
"""Unit tests for the JSON-lines operational logging channel."""

from __future__ import annotations

import io
import json
import logging
from collections.abc import Iterator
from pathlib import Path

import pytest

from modelfoundry.logging import JsonFormatter, get_logger


@pytest.fixture(autouse=True)
def _reset_package_logger() -> Iterator[None]:
    """Strip handlers/level off the package logger before and after each test.

    `get_logger` mutates the process-global `modelfoundry` logger; isolate tests
    so handler accumulation in one does not leak into the next.
    """
    pkg = logging.getLogger("modelfoundry")
    saved = (list(pkg.handlers), pkg.level)
    pkg.handlers.clear()
    pkg.setLevel(logging.NOTSET)
    yield
    pkg.handlers.clear()
    pkg.handlers.extend(saved[0])
    pkg.setLevel(saved[1])


def test_emitted_line_is_valid_json_with_core_fields() -> None:
    stream = io.StringIO()
    logger = get_logger(target=stream, level=logging.INFO)
    logger.info("hello world")
    record = json.loads(stream.getvalue().strip())
    assert set(record) >= {"timestamp", "level", "logger", "message"}
    assert record["level"] == "INFO"
    assert record["logger"] == "modelfoundry"
    assert record["message"] == "hello world"


def test_timestamp_is_utc_iso8601_z() -> None:
    stream = io.StringIO()
    logger = get_logger(target=stream, level=logging.INFO)
    logger.info("tick")
    record = json.loads(stream.getvalue().strip())
    assert record["timestamp"].endswith("Z")


def test_extra_fields_are_honoured() -> None:
    stream = io.StringIO()
    logger = get_logger(target=stream, level=logging.INFO)
    logger.info("stage start", extra={"stage": "training", "epoch": 3})
    record = json.loads(stream.getvalue().strip())
    assert record["stage"] == "training"
    assert record["epoch"] == 3


def test_extra_cannot_shadow_core_fields() -> None:
    stream = io.StringIO()
    logger = get_logger(target=stream, level=logging.INFO)
    logger.info("guarded", extra={"level": "BOGUS"})
    record = json.loads(stream.getvalue().strip())
    assert record["level"] == "INFO"


def test_named_logger_is_namespaced_under_package() -> None:
    stream = io.StringIO()
    get_logger(target=stream, level=logging.INFO)
    child = get_logger("pipeline.runner")
    child.info("from child")
    record = json.loads(stream.getvalue().strip())
    assert record["logger"] == "modelfoundry.pipeline.runner"


def test_target_can_be_a_file(tmp_path: Path) -> None:
    log_file = tmp_path / "ops.jsonl"
    logger = get_logger(target=log_file, level=logging.INFO)
    logger.info("to file", extra={"stage": "validate"})
    for handler in logging.getLogger("modelfoundry").handlers:
        handler.flush()
    lines = [ln for ln in log_file.read_text().splitlines() if ln]
    assert len(lines) == 1
    record = json.loads(lines[0])
    assert record["message"] == "to file"
    assert record["stage"] == "validate"


def test_retargeting_replaces_prior_json_handler() -> None:
    first = io.StringIO()
    get_logger(target=first, level=logging.INFO)
    second = io.StringIO()
    logger = get_logger(target=second)
    logger.info("only in second")
    assert first.getvalue() == ""
    assert "only in second" in second.getvalue()


def test_root_logger_is_never_touched() -> None:
    root_before = list(logging.getLogger().handlers)
    get_logger(target=io.StringIO())
    assert logging.getLogger().handlers == root_before


def test_exc_info_is_captured() -> None:
    stream = io.StringIO()
    logger = get_logger(target=stream, level=logging.INFO)
    try:
        raise ValueError("boom")
    except ValueError:
        logger.exception("caught it")
    record = json.loads(stream.getvalue().strip())
    assert "exc_info" in record
    assert "ValueError: boom" in record["exc_info"]


def test_formatter_is_jsonformatter_instance() -> None:
    logger = get_logger(target=io.StringIO())
    pkg = logging.getLogger("modelfoundry")
    assert any(isinstance(h.formatter, JsonFormatter) for h in pkg.handlers)
    assert logger.name == "modelfoundry"
