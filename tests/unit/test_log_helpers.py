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
import gttk.utils.log_helpers as log_helpers_module
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
        for sample in UNICODE_LOG_SAMPLES:
            logger.info(sample)  # Would raise UnicodeEncodeError without fix

        # Read output before shutdown — Utf8StreamHandler wraps our buffer, so
        # tearing it down cascade-closes the BytesIO.
        output = buf.getvalue()
        shutdown_logger(logger)

        assert output, "Logger produced no output on cp1252 stdout"

    def test_setup_logger_emits_utf8_bytes(self, monkeypatch):
        """Utf8StreamHandler should write UTF-8 encoded bytes regardless of
        the wrapping TextIOWrapper's declared encoding."""
        buf = io.BytesIO()
        fake_stdout = io.TextIOWrapper(
            buf, encoding='utf-8', errors='strict',
            line_buffering=True, write_through=True,
        )
        monkeypatch.setattr(sys, 'stdout', fake_stdout)

        logger = setup_logger()
        logger.info("pixels \u2264 threshold")

        output = buf.getvalue()
        shutdown_logger(logger)

        # ≤ encoded as UTF-8 is 0xE2 0x89 0xA4
        assert b'\xe2\x89\xa4' in output

    def test_setup_logger_tolerates_stream_without_buffer(self, monkeypatch):
        """Some IDE consoles wrap stdout in objects that lack a .buffer
        attribute; Utf8StreamHandler must fall back to using the stream
        directly rather than raising."""
        class StreamWithoutBuffer:
            def __init__(self):
                self.chunks = []
            def write(self, s):
                self.chunks.append(s)
                return len(s)
            def flush(self):
                pass
            # Deliberately no .buffer attribute

        fake_stdout = StreamWithoutBuffer()
        monkeypatch.setattr(sys, 'stdout', fake_stdout)

        logger = setup_logger()
        logger.info("hello world")  # ASCII only — no wrapping possible

        assert any("hello world" in chunk for chunk in fake_stdout.chunks)
        shutdown_logger(logger)


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


def _pipe_like_stdout():
    """stdout as a subprocess sees it: block-buffered text over a buffered byte stream."""
    raw = io.BytesIO()
    return raw, io.TextIOWrapper(io.BufferedWriter(raw), encoding='utf-8')


@pytest.mark.unit
class TestUtf8StreamHandlerOrdering:
    """The handler writes bytes beneath the text layer, so whatever the text layer
    still holds has to go down first or a record lands in the middle of it."""

    def test_record_lands_after_a_pending_newline(self, monkeypatch):
        """print() of a line longer than the text layer's 8 KiB chunk pushes the text
        down at once but keeps the newline pending; the next record used to be written
        between them. That is how gdal_runner's JSON line reached ArcGIS Pro with
        'All commands executed successfully.' glued to its end."""
        raw, stdout = _pipe_like_stdout()
        monkeypatch.setattr(sys, 'stdout', stdout)
        logger = setup_logger()
        try:
            print('{"stdout": "' + 'x' * 9000 + '"}', file=sys.stdout)
            logger.info("All commands executed successfully.")
            sys.stdout.flush()
        finally:
            shutdown_logger(logger)
        lines = raw.getvalue().decode('utf-8').split('\n')
        assert lines[0].endswith('"}'), lines[0][-60:]
        assert lines[1] == "All commands executed successfully."
        assert lines[2] == ""

    def test_record_does_not_overtake_short_pending_text(self, monkeypatch):
        """A short print() stays entirely pending in the text layer; a record written
        beneath it would come out first."""
        raw, stdout = _pipe_like_stdout()
        monkeypatch.setattr(sys, 'stdout', stdout)
        logger = setup_logger()
        try:
            print("first", file=sys.stdout)
            logger.info("second")
            sys.stdout.flush()
        finally:
            shutdown_logger(logger)
        assert raw.getvalue().decode('utf-8') == "first\nsecond\n"


class TestNoArcpyInitialiser:
    """``init_arcpy()`` imported a top-level ``utils`` package that has never existed. The
    ImportError it swallowed ended the function before ``arcpy.env.overwriteOutput`` was
    set, so the three tools that called it under ArcGIS Pro got nothing from it. It is
    gone, along with ``arcgis_proj_config``, a module nothing imported."""

    def test_nothing_in_the_package_initialises_arcpy(self):
        import importlib.util
        import pathlib
        package = pathlib.Path(log_helpers_module.__file__).resolve().parents[1]
        assert not hasattr(log_helpers_module, 'init_arcpy')
        offenders = [path.name for path in package.rglob('*.py')
                     if 'init_arcpy' in path.read_text(encoding='utf-8')]
        assert offenders == []
        assert importlib.util.find_spec('gttk.utils.arcgis_proj_config') is None
