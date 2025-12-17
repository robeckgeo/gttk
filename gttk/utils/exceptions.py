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
Custom Exceptions Module.

A centralized module for custom exceptions used throughout the GeoTIFF ToolKit.
"""

class ProcessingStepFailedError(RuntimeError):
    """Custom exception raised for errors during a GeoTIFF processing step."""
    pass

class TransparencyProcessingError(Exception):
    """Base exception for errors during transparency processing."""
    pass

class ValidateCOGError(Exception):
    """Custom exception for errors during COG validation."""
    pass

class GdalExecutionError(RuntimeError):
    """Custom exception for errors during GDAL command execution."""
    pass

class CompressionTestError(Exception):
    """Base exception for compression testing errors."""
    pass

class CSVLoadError(CompressionTestError):
    """Error loading compression options CSV."""
    pass

class OptimizationError(CompressionTestError):
    """Error during GeoTIFF optimization process."""
    pass