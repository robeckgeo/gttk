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
This module provides logging helpers for the GeoTIFF ToolKit, including
support for both CLI and ArcGIS Pro environments.

Everything here operates on the ``gttk`` logger, never the root logger: an importing
application owns root, and GTTK reconfiguring it used to disable that application's
logging as a side effect of an import.
"""

import logging
import os
import sys
from typing import Optional, TYPE_CHECKING

if TYPE_CHECKING:
    import arcpy # type: ignore


class Utf8StreamHandler(logging.StreamHandler):
    """A StreamHandler that writes UTF-8 bytes directly to the stream's
    binary buffer, with errors='replace'.

    Bypasses Windows cp1252 console limitations without mutating sys.stdout
    or wrapping it in a new TextIOWrapper (which would cascade-close the
    underlying buffer on teardown). Falls back to the default text-mode
    write if the stream exposes no .buffer attribute.

    Writing beneath the text layer means anything still pending in that layer
    must be flushed first, or a record can land in the middle of it; emit()
    does so before every write.

    sys.stdout.reconfigure() would be simpler but silently no-ops on some
    Windows console setups (observed with Python 3.12 + conda + cmd.exe),
    so we encode explicitly.
    """
    def emit(self, record):
        try:
            msg = self.format(record)
            stream = self.stream
            buffer = getattr(stream, 'buffer', None)
            if buffer is not None:
                try:
                    # Whatever the text layer still holds must go down first. print()
                    # leaves a lone newline pending after a write longer than its 8 KiB
                    # chunk; writing beneath it put this record between a line and its
                    # newline -- which is how gdal_runner's JSON line reached its parent
                    # with "All commands executed successfully." glued to the end.
                    stream.flush()
                    buffer.write((msg + self.terminator).encode('utf-8', errors='replace'))
                    buffer.flush()
                    return
                except (AttributeError, ValueError, OSError):
                    pass  # Fall through to text-mode write
            stream.write(msg + self.terminator)
            self.flush()
        except RecursionError:
            raise
        except Exception:
            self.handleError(record)


class ArcpyLogHandler(logging.Handler):
    """A custom logging handler that redirects log messages to arcpy."""
    def emit(self, record):
        try:
            # Lazy import arcpy only when a message is emitted
            import arcpy # type: ignore
            msg = self.format(record)
            if record.levelno >= logging.ERROR:
                arcpy.AddError(f'ERROR: {msg}')
            elif record.levelno >= logging.WARNING:
                arcpy.AddWarning(f'WARNING: {msg}')
            else:
                arcpy.AddMessage(msg)
        except (ImportError, RuntimeError):
            # This will handle cases where arcpy is not available or initialized
            sys.stderr.write(f"ArcpyLogHandler Error (arcpy not available): {self.format(record)}\n")
        except Exception as e:
            sys.stderr.write(f"ArcpyLogHandler Error: {e}\n")

#: Every GTTK module logs under this name, so configuring it configures GTTK and
#: nothing else.
PACKAGE_LOGGER = 'gttk'


def setup_logger(log_file: Optional[str] = None, is_arc_mode: bool = False,
                 level: int = logging.INFO, quiet_matplotlib: bool = True) -> logging.Logger:
    """
    Set up and configure GTTK's own logger.

    Configures ``logging.getLogger('gttk')``, **not** the root logger. Clearing root's
    handlers -- which this used to do -- silently disabled the logging of any
    application that imported GTTK. An application that never calls this gets GTTK's
    messages through its own root handlers by normal propagation, which is what a
    library should do; calling this is opting in to GTTK managing its own output.

    Args:
        log_file (str, optional): The full path to the log file.
        is_arc_mode (bool): If True, configures logging for the ArcGIS environment.
        level (int): The logging level.
        quiet_matplotlib (bool): Raise matplotlib's own logger to WARNING. On by default
            because GTTK renders histograms and matplotlib is noisy at DEBUG; pass False
            to leave another library's logger alone.

    Returns:
        logging.Logger: The configured ``gttk`` logger.
    """
    logger = logging.getLogger(PACKAGE_LOGGER)
    logger.setLevel(level)

    for handler in logger.handlers[:]:
        logger.removeHandler(handler)
    # GTTK now owns its own output, so do not also hand it to the application's root
    # handlers -- that would print every message twice.
    logger.propagate = False

    formatter = logging.Formatter('%(message)s')
    file_formatter = logging.Formatter('%(asctime)s - %(name)s - %(levelname)s - %(message)s')

    if is_arc_mode:
        handler = ArcpyLogHandler()
        handler.setFormatter(formatter)
        logger.addHandler(handler)
    else:
        handler = Utf8StreamHandler(sys.stdout)
        handler.setFormatter(formatter)
        logger.addHandler(handler)

    if log_file:
        log_dir = os.path.dirname(log_file)
        if log_dir:
            os.makedirs(log_dir, exist_ok=True)

        file_handler = logging.FileHandler(log_file, mode='w')
        file_handler.setLevel(logging.INFO)
        file_handler.setFormatter(file_formatter)
        logger.addHandler(file_handler)

    if quiet_matplotlib:
        logging.getLogger('matplotlib').setLevel(logging.WARNING)

    return logger

def shutdown_logger(logger: logging.Logger):
    """
    Safely shuts down a logger by removing and closing its handlers.
    This is crucial for releasing file locks.

    Also restores propagation, so a later import of GTTK by the same process behaves
    like a fresh one.
    """
    if not logger:
        return
    if logger.name == PACKAGE_LOGGER:
        logger.propagate = True
    handlers = logger.handlers[:]
    for handler in handlers:
        handler.flush()
        handler.close()
        logger.removeHandler(handler)

def init_arcpy() -> None:
    """
    Initialize ArcPy module and set overwrite output to True.
    This function is called when running in ArcGIS environment.
    """
    try:
        import arcpy # type: ignore
        import importlib
        from utils import statistics
        importlib.reload(statistics)
        arcpy.env.overwriteOutput = True
    except ImportError:
        pass