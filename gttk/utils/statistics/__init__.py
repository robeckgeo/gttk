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
Statistics Package - Public API.

This package provides comprehensive raster statistics calculation with automatic
strategy selection between fast single-pass and blocked multi-pass approaches.

Main Functions:
    calculate_statistics: Calculate statistics with automatic strategy selection
    write_pam_xml: Write PAM XML (.aux.xml) file
    build_pam_data_from_stats: Convert StatisticsBand to PAM format
    generate_histogram_base64: Generate histogram visualization (matplotlib)

Classes:
    OnlineStatistics: Accumulate statistics across blocks
    OnlineHistogram: Accumulate histogram counts across blocks
    AlphaCharacteristics: Track alpha band characteristics

Example:
    >>> from gttk.utils.statistics import calculate_statistics
    >>> from osgeo import gdal
    >>> 
    >>> ds = gdal.Open('image.tif')
    >>> stats = calculate_statistics(ds)
    >>> for band_stat in stats:
    >>>     print(f"{band_stat.band_name}: mean={band_stat.mean:.2f}")
"""

# Main functions
from .calculator import calculate_statistics

# PAM XML functions
from .pam_writer import write_pam_xml, build_pam_data_from_stats

# Histogram visualization
from .histogram_generator import generate_histogram_base64

# Classes and private functions (for tests and advanced usage)
from .online_accumulators import (
    OnlineStatistics,
    OnlineHistogram,
    AlphaCharacteristics,
)

# Type utilities (for tests)
from .helpers import (
    GDAL_TO_NUMPY_DTYPE,
    _calculate_max_pixels_threshold,
    _calculate_histogram_bins,
    _get_optimal_dtype,
    _iterate_blocks,
    _promote_for_statistics,
    _safe_nodata_comparison,
    format_number,
)

# Configuration constants
from .helpers import (
    DEFAULT_BLOCK_SIZE,
    DEFAULT_MAX_PIXELS,
)

# Internal functions (for tests - mark as private in docs)
from .calculator import (
    _calculate_statistics_blocked,
    _calculate_statistics_full,
)

__all__ = [
    # Main API
    'calculate_statistics',
    'generate_histogram_base64',
    'build_pam_data_from_stats',
    'write_pam_xml',
    
    # Classes
    'OnlineStatistics',
    'OnlineHistogram',
    'AlphaCharacteristics',
    
    # Constants
    'DEFAULT_BLOCK_SIZE',
    'DEFAULT_MAX_PIXELS',
    'GDAL_TO_NUMPY_DTYPE',
    
    # Internal functions (available but not recommended for public use)
    '_calculate_statistics_blocked',
    '_calculate_statistics_full',
    '_calculate_histogram_bins',
    '_calculate_max_pixels_threshold',
    '_get_optimal_dtype',
    '_iterate_blocks',
    '_promote_for_statistics',
    '_safe_nodata_comparison',
    'format_number',
]

__version__ = '1.0.0'
__author__ = 'Eric Robeck'
