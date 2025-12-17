#!/usr/bin/env python3
# -*- coding: utf-8 -*-
# ******************************************************************************
# Project: GeoTIFF ToolKit (GTTK)
# Author: Eric Robeck <robeckgeo@gmail.com>
#
# Copyright (c) 2025, Eric Robeck
# Licensed under the MIT License
# ******************************************************************************

"""
This module provides logging helpers for the GeoTIFF ToolKit, including
support for both CLI and ArcGIS Pro environments.
"""

import logging
import os
import sys
from typing import Optional, TYPE_CHECKING

if TYPE_CHECKING:
    import arcpy # type: ignore

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

def setup_logger(log_file: Optional[str] = None, is_arc_mode: bool = False, level: int = logging.INFO) -> logging.Logger:
    """
    Set up and configure the root logger.

    Args:
        log_file (str, optional): The full path to the log file.
        is_arc_mode (bool): If True, configures logging for the ArcGIS environment.
        level (int): The logging level.

    Returns:
        logging.Logger: The configured root logger instance.
    """
    logger = logging.getLogger()
    logger.setLevel(level)

    if logger.hasHandlers():
        logger.handlers.clear()

    formatter = logging.Formatter('%(message)s')
    file_formatter = logging.Formatter('%(asctime)s - %(name)s - %(levelname)s - %(message)s')

    if is_arc_mode:
        handler = ArcpyLogHandler()
        handler.setFormatter(formatter)
        logger.addHandler(handler)
    else:
        handler = logging.StreamHandler(sys.stdout)
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

    # Quieting matplotlib's verbose logging
    logging.getLogger('matplotlib').setLevel(logging.WARNING)
    
    return logger

def shutdown_logger(logger: logging.Logger):
    """
    Safely shuts down a logger by removing and closing its handlers.
    This is crucial for releasing file locks.
    """
    if not logger:
        return
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
        from utils import statistics_calculator, histogram_generator
        importlib.reload(statistics_calculator)
        importlib.reload(histogram_generator)
        arcpy.env.overwriteOutput = True
    except ImportError:
        pass