#!/usr/bin/env python3
# -*- coding: utf-8 -*-
# ******************************************************************************
# Project: GeoTIFF ToolKit (GTTK)
# Author: Eric Robeck <robeckgeo@gmail.com>
#
# Copyright (c) 2026, Eric Robeck
# Licensed under the MIT License
# ******************************************************************************

"""
Unit tests for GTTK logging helpers and startup env checks.

Covers:
- setup_logger() tolerance of Windows cp1252 consoles (regression test for
  UnicodeEncodeError on math symbols and emoji in log messages).
- _check_proj_env() one-shot PROJ env sanity warning, accepting either the
  modern PROJ_DATA variable or the legacy PROJ_LIB variable.
"""

import io
import logging
import sys

import pytest

from gttk.main import _check_proj_env
from gttk.utils.log_helpers import setup_logger, shutdown_logger


# Unicode characters that appear in gttk log messages today. These are the
# exact codepoints that triggered UnicodeEncodeError on a cp1252 console.
UNICODE_LOG_SAMPLES = [
    "pixels \u2264 threshold",   # ≤ in statistics/calculator.py
    "dims \u00d7 dims",          # × in statistics/calculator.py
    "bytes \u2192 overhead",     # → in geotiff_processor.py
    "time \u00b1 stddev",        # ± in test_compression.py
    "Result: \u274c FAIL",       # ❌ in validate_metadata.py
    "Result: \u2705 PASS",       # ✅ in validate_metadata.py
    "Result: \u26a0\ufe0f SKIP", # ⚠️ in validate_metadata.py
]


@pytest.mark.unit
class TestSetupLoggerCp1252Tolerance:
    """setup_logger() must not raise UnicodeEncodeError on cp1252 consoles."""

    def test_setup_logger_handles_unicode_on_cp1252_stdout(self, monkeypatch):
        """Regression: every Unicode character used in gttk log messages must
        round-trip through setup_logger() without raising on a cp1252 stdout."""
        # Simulate a Windows PowerShell cp1252 console
        buf = io.BytesIO()
        fake_stdout = io.TextIOWrapper(
            buf, encoding='cp1252', errors='strict',
            line_buffering=True, write_through=True,
        )
        monkeypatch.setattr(sys, 'stdout', fake_stdout)

        logger = setup_logger()
        try:
            for sample in UNICODE_LOG_SAMPLES:
                logger.info(sample)  # Would raise UnicodeEncodeError without fix
        finally:
            shutdown_logger(logger)

        fake_stdout.flush()
        # Buffer should be non-empty — the fix either re-encoded as UTF-8 or
        # substituted replacement chars; either way, no exception was raised.
        assert buf.getvalue(), "Logger produced no output on cp1252 stdout"

    def test_setup_logger_on_utf8_stdout_is_unchanged(self, monkeypatch):
        """The reconfigure should be a no-op on streams that are already UTF-8."""
        buf = io.BytesIO()
        fake_stdout = io.TextIOWrapper(
            buf, encoding='utf-8', errors='strict',
            line_buffering=True, write_through=True,
        )
        monkeypatch.setattr(sys, 'stdout', fake_stdout)

        logger = setup_logger()
        try:
            logger.info("pixels \u2264 threshold")
        finally:
            shutdown_logger(logger)

        fake_stdout.flush()
        # ≤ encoded as UTF-8 is 0xE2 0x89 0xA4
        assert b'\xe2\x89\xa4' in buf.getvalue()

    def test_setup_logger_tolerates_stream_without_reconfigure(self, monkeypatch):
        """Some IDE consoles wrap stdout in objects that lack reconfigure();
        setup_logger() must degrade gracefully."""
        class StreamWithoutReconfigure:
            def __init__(self):
                self.buf = []
            def write(self, s):
                self.buf.append(s)
                return len(s)
            def flush(self):
                pass
            # Deliberately no reconfigure() attribute

        fake_stdout = StreamWithoutReconfigure()
        monkeypatch.setattr(sys, 'stdout', fake_stdout)

        logger = setup_logger()
        try:
            logger.info("hello world")  # ASCII only — stream can't reconfigure
        finally:
            shutdown_logger(logger)

        assert any("hello world" in chunk for chunk in fake_stdout.buf)


@pytest.mark.unit
class TestCheckProjEnv:
    """_check_proj_env() warns iff neither PROJ_DATA nor PROJ_LIB is set."""

    def test_warns_when_neither_is_set(self, monkeypatch, caplog):
        monkeypatch.delenv('PROJ_DATA', raising=False)
        monkeypatch.delenv('PROJ_LIB', raising=False)

        with caplog.at_level(logging.WARNING, logger='gttk.main'):
            _check_proj_env()

        assert any('Neither PROJ_DATA nor PROJ_LIB' in r.message for r in caplog.records)

    def test_silent_when_proj_data_is_set(self, monkeypatch, caplog):
        monkeypatch.setenv('PROJ_DATA', '/some/path/to/proj')
        monkeypatch.delenv('PROJ_LIB', raising=False)

        with caplog.at_level(logging.WARNING, logger='gttk.main'):
            _check_proj_env()

        assert not any('PROJ' in r.message for r in caplog.records)

    def test_silent_when_proj_lib_is_set(self, monkeypatch, caplog):
        """Legacy PROJ_LIB still counts — PROJ 8+ honors it for backcompat."""
        monkeypatch.delenv('PROJ_DATA', raising=False)
        monkeypatch.setenv('PROJ_LIB', '/some/path/to/proj')

        with caplog.at_level(logging.WARNING, logger='gttk.main'):
            _check_proj_env()

        assert not any('PROJ' in r.message for r in caplog.records)

    def test_silent_when_both_are_set(self, monkeypatch, caplog):
        monkeypatch.setenv('PROJ_DATA', '/some/path/to/proj')
        monkeypatch.setenv('PROJ_LIB', '/some/other/path')

        with caplog.at_level(logging.WARNING, logger='gttk.main'):
            _check_proj_env()

        assert not any('PROJ' in r.message for r in caplog.records)
