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
Statistics Helpers and Utilities.

Utility functions, type system, configuration constants, and block iteration
support for statistics calculation.

Constants:
    DEFAULT_MAX_PIXELS: Default threshold for fast path (268M pixels)
    DEFAULT_BLOCK_SIZE: Default block size for blocked processing
    GDAL_TO_NUMPY_DTYPE: Mapping from GDAL to NumPy data types
    NUMBA_AVAILABLE: Whether Numba JIT is available

Functions:
    _calculate_max_pixels_threshold: RAM-based threshold calculation
    _get_optimal_dtype: Get optimal numpy dtype for band
    _safe_nodata_comparison: Dtype-aware nodata masking
    _promote_for_statistics: Promote to float64 for statistics
    _iterate_blocks: Iterate over raster in blocks
    format_number: Format numbers with separators
    _calculate_histogram_bins: Calculate histogram bins
"""

import numpy as np
from osgeo import gdal
import logging
from typing import Optional
from gttk.utils.config_loader import config

# Configure logging
logger = logging.getLogger(__name__)

# ============================================================================
# CONFIGURATION CONSTANTS
# ============================================================================

# Default maximum pixels per band for fast path (16,384² = 268,435,456 pixels)
# This is conservative for 16GB systems with 4-band int16 imagery
DEFAULT_MAX_PIXELS = 268_435_456

# Default block size for blocked processing (4096×4096 = 16,777,216 pixels)
# Balanced for RAM safety on 16GB systems while still providing good performance
# - Float32 4-band: ~268MB per block (safe for 16GB RAM)
# - Triggers Numba JIT for large images (>100M pixels total)
DEFAULT_BLOCK_SIZE = (4096, 4096)

# ============================================================================
# THRESHOLD CALCULATION (RAM-Based Auto-Detection)
# ============================================================================

def _calculate_max_pixels_threshold(available_ram_gb: Optional[float] = None) -> int:
    """
    Calculate maximum pixels threshold for fast path based on available RAM.
    
    Uses realistic estimates based on common data types:
    - Most common: 4-band Byte imagery (RGB+Alpha or multispectral): 1 byte/pixel
    - 4-band UInt16 imagery (satellite data): 2 bytes/pixel
    - Single-band Float32 (DEMs, scientific data): 4 bytes/pixel
    
    Memory model:
    - Native dtype for full image load (varies by type)
    - Float64 for valid pixels after masking (~90% of image, 8 bytes/pixel)
    - Temporary arrays during statistics (2.5× safety factor for NumPy operations)
    - Uses 25% of available RAM for statistics processing
    
    Conservative assumption: 4-band Int16 worst case
    - Native load: 4 bands × 2 bytes × total_pixels = 8 bytes/pixel
    - Stats on valid (90%): 4 bands × 8 bytes × 0.9 × total_pixels = 28.8 bytes/pixel
    - With 2.5× safety: (8 + 28.8) × 2.5 = 92 bytes/pixel total
    
    Args:
        available_ram_gb: Available RAM in GB (None = auto-detect with psutil)
        
    Returns:
        Maximum pixels per band for fast path processing
        Clamped to range [67,108,864 to 1,073,741,824] (8,192² to 32,768²)
        
    Example:
        >>> # System with 16 GB available RAM
        >>> _calculate_max_pixels_threshold(16.0)
        268435456  # 16,384² pixels (conservative for 4-band UInt16)
    """
    # Try to get from config first (0 or negative means auto-detect)
    config_max_pixels = config.get("statistics.max_pixels_fast_path", 0)
    if config_max_pixels > 0:
        logger.info(f"Using max_pixels from config: {config_max_pixels:,}")
        return int(config_max_pixels)
    
    # Auto-detect based on available RAM
    if available_ram_gb is None:
        try:
            import psutil
            available_ram_gb = psutil.virtual_memory().available / (1024**3)
            logger.info(f"Detected available RAM: {available_ram_gb:.2f} GB")
        except ImportError:
            logger.info("psutil not available - using default threshold (268M pixels)")
            return DEFAULT_MAX_PIXELS
        except Exception as e:
            logger.warning(f"Error detecting available RAM: {e}, using default threshold")
            return DEFAULT_MAX_PIXELS
    
    # Conservative calculation: use 25% of available RAM
    # Memory model for 4-band UInt16 (common satellite imagery):
    #   - Native load: 4 bands × 2 bytes = 8 bytes/pixel
    #   - Stats array (float64): 4 bands × 8 bytes = 32 bytes/pixel
    #   - Temporary arrays: 1.5× safety factor
    #   - Total: (8 + 32) × 1.5 = 60 bytes/pixel
    max_gb_usage = available_ram_gb * 0.25
    bytes_per_pixel = 60  # Realistic estimate for 4-band UInt16
    max_pixels = int((max_gb_usage * 1024**3) / bytes_per_pixel)

    # Clamp to reasonable range: 8,192² to 32,768²
    max_pixels = max(67_108_864, min(max_pixels, 1_073_741_824))
    
    logger.info(f"Calculated max_pixels threshold: {max_pixels:,} pixels "
                f"(based on {available_ram_gb:.2f} GB RAM, using 25% for statistics)")
    return max_pixels

# ============================================================================
# TYPE SYSTEM UTILITIES (Native Data Type Support)
# ============================================================================

# GDAL to NumPy data type mapping for native type processing
GDAL_TO_NUMPY_DTYPE = {
    gdal.GDT_Byte: np.uint8,
    gdal.GDT_Int16: np.int16,
    gdal.GDT_UInt16: np.uint16,
    gdal.GDT_Int32: np.int32,
    gdal.GDT_UInt32: np.uint32,
    gdal.GDT_Float32: np.float32,
    gdal.GDT_Float64: np.float64,
}

def _get_optimal_dtype(band: gdal.Band) -> np.dtype:
    """
    Get optimal numpy dtype for band's GDAL type.
    
    Uses native data types instead of always promoting to float64,
    providing 50-87% memory reduction for typical imagery.
    
    Args:
        band: GDAL Band object
        
    Returns:
        NumPy dtype matching the band's native type (fallback to float64)
        
    Examples:
        - Byte data (RGB imagery) → np.uint8 (87.5% memory savings vs float64)
        - UInt16 (multispectral, DEMs) → np.uint16 (75% memory savings)
        - Float32 (scientific data) → np.float32 (50% memory savings)
    """
    return GDAL_TO_NUMPY_DTYPE.get(band.DataType, np.float64)

def _safe_nodata_comparison(data: np.ndarray, nodata_value: Optional[float],
                            dtype: np.dtype) -> np.ndarray:
    """
    Compare data to nodata value with dtype-aware logic.
    
    Handles different data types correctly:
    - NaN nodata values (for float types)
    - Precision issues (float comparison tolerance)
    - Integer exact comparison
    
    Args:
        data: NumPy array of pixel data
        nodata_value: NoData value from band metadata (None if not set)
        dtype: Native dtype of the data array
        
    Returns:
        Boolean mask array where True indicates nodata pixels
        
    Examples:
        >>> # Integer data with nodata=-9999
        >>> _safe_nodata_comparison(int16_array, -9999, np.int16)
        
        >>> # Float data with NaN nodata
        >>> _safe_nodata_comparison(float32_array, np.nan, np.float32)
    """
    if nodata_value is None:
        # No nodata metadata, only NaN pixels
        if np.issubdtype(dtype, np.floating):
            return np.isnan(data)
        return np.zeros_like(data, dtype=bool)
    
    # NaN nodata value (float types only)
    if np.isnan(nodata_value):
        return np.isnan(data)
    
    # Integer types: exact comparison
    if np.issubdtype(dtype, np.integer):
        # Convert nodata to native type for comparison
        # Handle both dtype objects and type classes
        dtype_obj = np.dtype(dtype) if not isinstance(dtype, np.dtype) else dtype
        nodata_native = dtype_obj.type(nodata_value)
        return (data == nodata_native) | np.isnan(data)
    
    # Float types: tolerance-based comparison + NaN
    else:
        # Use small relative tolerance for float comparison
        tolerance = np.finfo(dtype).eps * 10
        return np.isclose(data, nodata_value, rtol=tolerance, atol=0) | np.isnan(data)

def _promote_for_statistics(data: np.ndarray) -> np.ndarray:
    """
    Promote data to float64 for statistics calculation.
    
    Prevents overflow in mean/std calculations and ensures
    precision for statistical operations. Only converts if needed.
    
    Args:
        data: NumPy array in native dtype
        
    Returns:
        NumPy array promoted to float64 (or original if already float64)
        
    Note:
        This function should only be called on valid (non-nodata) pixels
        after masking, to minimize memory usage during promotion.
        
    Examples:
        >>> uint8_data = np.array([100, 150, 200], dtype=np.uint8)
        >>> promoted = _promote_for_statistics(uint8_data)
        >>> promoted.dtype
        dtype('float64')
    """
    if data.dtype == np.float64:
        return data
    return data.astype(np.float64)

# ============================================================================
# BLOCK INFRASTRUCTURE (Large File Support)
# ============================================================================

def _iterate_blocks(band: gdal.Band, block_size: tuple = (4096, 4096)):
    """
    Iterate over raster band in blocks for memory-efficient processing.
    
    Yields blocks of raster data, handling edge cases where blocks may be
    smaller than block_size at image boundaries. Reads data in native dtype
    for memory efficiency.
    
    Args:
        band: GDAL Band object to read
        block_size: (height, width) of blocks in pixels
                    Default: (4096, 4096) = 16.7MP blocks (safe for 16GB RAM)
        
    Yields:
        Tuple of (block_data, x_offset, y_offset, x_size, y_size)
        - block_data: NumPy array in native dtype
        - x_offset, y_offset: Position of block in full raster
        - x_size, y_size: Actual size of block (may be smaller at edges)
        
    Example:
        >>> band = dataset.GetRasterBand(1)
        >>> for block, x_off, y_off, x_sz, y_sz in _iterate_blocks(band):
        >>>     # Process block
        >>>     print(f"Block at ({x_off}, {y_off}), size {x_sz}x{y_sz}")
    """
    block_height, block_width = block_size
    band_width = band.XSize
    band_height = band.YSize
    
    native_dtype = _get_optimal_dtype(band)
    
    # Iterate over rows of blocks
    for y_offset in range(0, band_height, block_height):
        y_size = min(block_height, band_height - y_offset)
        
        # Iterate over columns of blocks
        for x_offset in range(0, band_width, block_width):
            x_size = min(block_width, band_width - x_offset)
            
            # Read block in native dtype for memory efficiency
            block_raw = band.ReadAsArray(
                xoff=x_offset, yoff=y_offset,
                win_xsize=x_size, win_ysize=y_size
            )
            
            if block_raw is None:
                logger.warning(f"Failed to read block at ({x_offset}, {y_offset})")
                continue
            
            block = block_raw.astype(native_dtype)
            
            yield (block, x_offset, y_offset, x_size, y_size)

# ============================================================================
# UTILITY FUNCTIONS
# ============================================================================

def format_number(num: float, decimals: int = 4) -> str:
    """Format a number with thousand separators and specified decimals."""
    if isinstance(num, int) or (isinstance(num, float) and num.is_integer()):
        return f"{int(num):,}"
    return f"{num:,.{decimals}f}"

def _calculate_histogram_bins(
    valid_data: np.ndarray,
    band: gdal.Band
) -> tuple:
    """
    Calculate optimal histogram bins and counts for visualization.
    
    Uses 256 bins for all byte data (0-255 integer values) to ensure
    consistent bin alignment across all bands including alpha.
    Uses Freedman-Diaconis rule for non-byte data (float, large integers).
    
    Args:
        valid_data: Numpy array of valid pixel values
        band: GDAL band object for metadata access
        
    Returns:
        Tuple of (counts_list, bins_list) for histogram visualization
    """
    if valid_data.size == 0:
        return ([], [])
    
    # Check if byte data (0-255 integer values)
    is_byte_data = (
        np.all(valid_data >= 0) and
        np.all(valid_data <= 255) and
        np.all(np.mod(valid_data, 1) == 0)
    )
    
    # BYTE DATA (RGB, Alpha, etc.): Use 256 bins with range 0-256
    if is_byte_data:
        num_bins = 256
        hist_min, hist_max = 0, 256
    
    # NON-BYTE DATA (Float, large integers): Use Freedman-Diaconis rule
    else:
        # Filter out potential infinite values that might have slipped through
        finite_mask = np.isfinite(valid_data)
        if not np.all(finite_mask):
            valid_data = valid_data[finite_mask]
            if valid_data.size == 0:
                return ([], [])

        q75, q25 = np.percentile(valid_data, [75, 25])
        iqr = q75 - q25
        
        if iqr > 0:
            bin_width = 2 * iqr * (valid_data.size ** (-1/3))
            if bin_width > 0:
                data_range = np.max(valid_data) - np.min(valid_data)
                try:
                    num_bins = int(np.ceil(data_range / bin_width))
                except OverflowError:
                    # Fallback for extreme ranges
                    num_bins = 100
                num_bins = min(num_bins, 100)
            else:
                num_bins = 100
        else:
            num_bins = 100
        
        hist_min = np.min(valid_data)
        hist_max = np.max(valid_data)
    
    # Calculate histogram
    bins = np.linspace(hist_min, hist_max, num_bins + 1)
    counts, bin_edges = np.histogram(valid_data, bins=bins)
    
    return (counts.tolist(), bin_edges.tolist())
