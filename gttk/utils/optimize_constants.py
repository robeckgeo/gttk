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
Shared Constants and Default Values for GeoTIFF Optimization.

This module centralizes default parameters and enumerations used throughout the
GTTK optimization tools. It provides a single source of truth for compression levels,
predictors, quality settings, and product-specific defaults.

Classes:
    CompressionAlgorithm: Enum for supported compression algorithms.
    ProductType: Enum for data types (DEM, Image, etc.).
"""
from enum import Enum

# --- Helper Accessors ---

def default_decimals_for(product_type: str, algorithm: str):
    # LERC doesn't use decimals
    if algorithm == CompressionAlgorithm.LERC.value:
        return None
    return DEFAULT_DECIMALS_BY_TYPE.get(product_type)

def default_max_z_error_for(product_type: str):
    return DEFAULT_MAX_Z_ERROR_BY_TYPE.get(product_type, 0)

def default_level_for(algorithm: str):
    return DEFAULT_LEVEL_BY_ALGORITHM.get(algorithm)

def default_predictor_for(product_type: str):
    return DEFAULT_PREDICTOR_BY_TYPE.get(product_type, DEFAULT_DEM_PREDICTOR)


# --- Enumerations ---

class CompressionAlgorithm(Enum):
    """Enumeration of supported compression algorithms."""
    JPEG = 'JPEG'
    JXL = 'JXL'
    LZW = 'LZW'
    DEFLATE = 'DEFLATE'
    ZSTD = 'ZSTD'
    LERC = 'LERC'
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
DEFAULT_THEMATIC_PREDICTOR = 'NONE' # 1

# Decimal precision by product_type
DEFAULT_DEM_DECIMALS = 2
DEFAULT_ERROR_DECIMALS = 1
DEFAULT_SCIENTIFIC_DECIMALS = 8


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
}
DEFAULT_LEVEL_BY_ALGORITHM = {
    CompressionAlgorithm.DEFLATE.value: DEFAULT_DEFLATE_LEVEL,
    CompressionAlgorithm.ZSTD.value: DEFAULT_ZSTD_LEVEL,
}

