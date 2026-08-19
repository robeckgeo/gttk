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
Shared Constants and Default Values for GeoTIFF Optimization.

This module centralizes default parameters and enumerations used throughout the
GTTK optimization tools. It provides a single source of truth for compression levels,
predictors, quality settings, and product-specific defaults.

Classes:
    CompressionAlgorithm: Enum for supported compression algorithms.
    ProductType: Enum for data types (DEM, Image, etc.).
"""
from enum import Enum
import math

# --- Helper Accessors ---

def default_decimals_for(product_type: str, algorithm: str):
    # LERC (and its DEFLATE/ZSTD variants) carry precision via max_z_error, not decimals
    if algorithm in (CompressionAlgorithm.LERC.value,
                     CompressionAlgorithm.LERC_DEFLATE.value,
                     CompressionAlgorithm.LERC_ZSTD.value):
        return None
    return DEFAULT_DECIMALS_BY_TYPE.get(product_type)

def default_max_z_error_for(product_type: str):
    return DEFAULT_MAX_Z_ERROR_BY_TYPE.get(product_type, 0)

def default_level_for(algorithm: str):
    return DEFAULT_LEVEL_BY_ALGORITHM.get(algorithm)

def default_predictor_for(product_type: str):
    return DEFAULT_PREDICTOR_BY_TYPE.get(product_type, DEFAULT_DEM_PREDICTOR)

def default_overview_resampling_for(product_type: str):
    """Resampling kernel for overview generation, by product type.

    NEAREST for categorical (thematic) and paletted (image) data, BILINEAR for
    continuous surfaces.  Callers may override; see ``--overview-resampling``.
    """
    return DEFAULT_OVERVIEW_RESAMPLING_BY_TYPE.get(product_type, 'BILINEAR')

def is_float_dtype(data_type) -> bool:
    """True when a GDAL data type name denotes floating point (Float32/Float64/CFloat*)."""
    return 'Float' in str(data_type)

def resolve_predictor(predictor, data_type):
    """Clamp a predictor to one the data type can actually carry.

    PREDICTOR=3 is the TIFF floating-point predictor and libtiff rejects it on
    integer samples, so an integer raster falls back to 2 (horizontal
    differencing).  Returns ``(predictor, warning_or_None)``.
    """
    if predictor is None:
        return None, None
    try:
        predictor = int(predictor)
    except (TypeError, ValueError):
        return DEFAULT_THEMATIC_PREDICTOR, (
            f"PREDICTOR={predictor!r} is not a valid GDAL value; using "
            f"{DEFAULT_THEMATIC_PREDICTOR} (no predictor)."
        )
    if predictor == 3 and not is_float_dtype(data_type):
        return 2, (
            f"PREDICTOR=3 is the floating-point predictor and is invalid for "
            f"{data_type} data; falling back to PREDICTOR=2."
        )
    return predictor, None

def discard_lsb_bits_for(decimals, vmax, mantissa_bits: int = 23) -> int:
    """Number of mantissa bits a DISCARD_LSB-style quantizer can clear while keeping the
    worst-case absolute error within the precision implied by ``decimals`` decimal places,
    for values up to magnitude ``vmax``. ``mantissa_bits`` is 23 for Float32, 52 for Float64.

    Round-to-nearest clearing of K of the M mantissa bits of a value with exponent E
    (2**E <= |v| < 2**(E+1)) gives a worst-case error of 2**(E-(M+1)+K); sizing K to the
    largest magnitude present keeps that <= 0.5 * 10**-decimals (half a unit in the last
    requested decimal place). Because the error is relative (magnitude-dependent), K is
    sized conservatively from the band's max magnitude.

    Returns 0 when nothing can be cleared (large vmax / tight precision / bad input) and
    clamps to the mantissa width.
    """
    if decimals is None or vmax is None:
        return 0
    vmax = abs(float(vmax))
    if vmax <= 0 or not math.isfinite(vmax):
        return 0
    # K <= mantissa_bits - floor(log2(vmax)) - decimals * log2(10)
    k = math.floor(mantissa_bits - math.floor(math.log2(vmax)) - int(decimals) * math.log2(10))
    return max(0, min(mantissa_bits, k))


# --- Enumerations ---

class CompressionAlgorithm(Enum):
    """Enumeration of supported compression algorithms."""
    JPEG = 'JPEG'
    JXL = 'JXL'
    LZW = 'LZW'
    DEFLATE = 'DEFLATE'
    ZSTD = 'ZSTD'
    LERC = 'LERC'
    LERC_DEFLATE = 'LERC_DEFLATE'  # benchmark-only candidate (not a user-facing --algorithm choice)
    LERC_ZSTD = 'LERC_ZSTD'        # benchmark-only candidate (not a user-facing --algorithm choice)
    NONE = 'NONE'

class ProductType(Enum):
    """Enumeration of supported product types for GeoTIFF optimization."""
    DEM = 'dem'
    IMAGE = 'image'
    ERROR = 'error'
    SCIENTIFIC = 'scientific'
    THEMATIC = 'thematic'


# --- Default Parameter Values ---

# Tile size
DEFAULT_TILE_SIZE = 512

# Compression quality and levels
DEFAULT_QUALITY = 90
DEFAULT_DEFLATE_LEVEL = 6
DEFAULT_ZSTD_LEVEL = 9

# Max Z-error values by product_type
DEFAULT_DEM_MAX_Z_ERROR = 0.01
DEFAULT_ERROR_MAX_Z_ERROR = 0.1
DEFAULT_SCIENTIFIC_MAX_Z_ERROR = 0.0

# Default predictor by product_type
DEFAULT_DEM_PREDICTOR = 2
DEFAULT_ERROR_PREDICTOR = 2
DEFAULT_SCIENTIFIC_PREDICTOR = 3
DEFAULT_THEMATIC_PREDICTOR = 1  # PREDICTOR=1 is "no predictor"; GDAL rejects 'NONE'
DEFAULT_IMAGE_PREDICTOR = 1

# Decimal precision by product_type. NO_ROUNDING ('none') is the sentinel for
# "keep full precision" (no base-10 rounding); see the --decimals CLI option.
NO_ROUNDING = 'none'
DEFAULT_DEM_DECIMALS = 2
DEFAULT_ERROR_DECIMALS = 1
DEFAULT_SCIENTIFIC_DECIMALS = NO_ROUNDING  # scientific data: preserve precision by default


# --- Default Mappings ---

DEFAULT_DECIMALS_BY_TYPE = {
    ProductType.DEM.value: DEFAULT_DEM_DECIMALS,
    ProductType.ERROR.value: DEFAULT_ERROR_DECIMALS,
    ProductType.SCIENTIFIC.value: DEFAULT_SCIENTIFIC_DECIMALS,
}

DEFAULT_MAX_Z_ERROR_BY_TYPE = {
    ProductType.DEM.value: DEFAULT_DEM_MAX_Z_ERROR,
    ProductType.ERROR.value: DEFAULT_ERROR_MAX_Z_ERROR,
    ProductType.SCIENTIFIC.value: DEFAULT_SCIENTIFIC_MAX_Z_ERROR,
}

DEFAULT_PREDICTOR_BY_TYPE = {
    ProductType.DEM.value: DEFAULT_DEM_PREDICTOR,
    ProductType.ERROR.value: DEFAULT_ERROR_PREDICTOR,
    ProductType.SCIENTIFIC.value: DEFAULT_SCIENTIFIC_PREDICTOR,
    ProductType.THEMATIC.value: DEFAULT_THEMATIC_PREDICTOR,
    ProductType.IMAGE.value: DEFAULT_IMAGE_PREDICTOR,
}

# Overview resampling by product_type.  Categorical rasters must never be
# interpolated: averaging class code 2 with class code 4 invents class code 3.
# The COG driver's own default is an interpolating kernel for any band without a
# colour table, so this has to be stated explicitly rather than relied upon.
DEFAULT_OVERVIEW_RESAMPLING_BY_TYPE = {
    ProductType.DEM.value: 'BILINEAR',
    ProductType.ERROR.value: 'BILINEAR',
    ProductType.SCIENTIFIC.value: 'BILINEAR',
    ProductType.THEMATIC.value: 'NEAREST',
    ProductType.IMAGE.value: 'NEAREST',
}

#: Resampling kernels GDAL accepts for overview generation.
OVERVIEW_RESAMPLING_CHOICES = (
    'NEAREST', 'AVERAGE', 'BILINEAR', 'CUBIC', 'CUBICSPLINE',
    'LANCZOS', 'MODE', 'RMS', 'GAUSS',
)

#: Resampling kernels that blend neighbouring pixels, and so must not be applied
#: to categorical data.
INTERPOLATING_RESAMPLING = frozenset({
    'AVERAGE', 'BILINEAR', 'CUBIC', 'CUBICSPLINE', 'LANCZOS', 'RMS', 'GAUSS',
})
DEFAULT_LEVEL_BY_ALGORITHM = {
    CompressionAlgorithm.DEFLATE.value: DEFAULT_DEFLATE_LEVEL,
    CompressionAlgorithm.ZSTD.value: DEFAULT_ZSTD_LEVEL,
}

