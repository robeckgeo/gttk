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
Statistics Calculator - Main Calculation Engine.

Main statistics calculation functions with automatic strategy selection between
fast single-pass and blocked multi-pass approaches.

Functions:
    calculate_statistics: Main entry point with automatic strategy selection
    _calculate_statistics_full: Fast path for small files (loads entire image)
    _calculate_statistics_blocked: Blocked path for large files (processes in chunks)
"""

import numpy as np
from osgeo import gdal
import logging
from typing import Optional, Union, List, Tuple

from gttk.utils.data_models import StatisticsBand
from gttk.utils.config_loader import config
from .online_accumulators import OnlineStatistics, OnlineHistogram, AlphaCharacteristics
from .helpers import (
    DEFAULT_BLOCK_SIZE,
    _calculate_max_pixels_threshold,
    _get_optimal_dtype,
    _safe_nodata_comparison,
    _promote_for_statistics,
    _iterate_blocks,
    _calculate_histogram_bins,
)
from .pam_writer import _get_pam_histogram

# Configure logging
logger = logging.getLogger(__name__)


def _calculate_statistics_blocked(
    ds_or_band: Union[gdal.Dataset, gdal.Band],
    block_size: tuple = (4096, 4096)
) -> Optional[List[StatisticsBand]]:
    """
    Block-based statistics calculation for large files.
    
    Uses optimized two-pass algorithm with intelligent alpha detection:
    - Pass 1: Determine histogram bins + analyze alpha characteristics + count alpha=0
    - Pass 2: Accumulate statistics with cached alpha/transparency masks
    
    Phase 2 Optimizations:
    - Merged Pass 0 into Pass 1 (eliminates one complete file read)
    - Intelligent alpha band detection (binary vs graduated transparency)
    - Caches alpha and transparency mask blocks (eliminates redundant reads)
    
    Performance: ~1.5x faster than 3-pass due to I/O reduction and mask caching.
    
    Args:
        ds_or_band: GDAL Dataset or Band to calculate statistics for
        block_size: Block dimensions for processing (height, width)
                    Default: (4096, 4096) = 16.7MP blocks (safe for 16GB RAM)
        
    Returns:
        List of StatisticsBand objects, one per band, or None if calculation fails
        
    Note:
        Median is not calculated in blocked mode to conserve memory.
        Histogram bins are determined from first pass min/max scan.
    """
    logger.info("Using block-based statistics calculation")
    logger.info("Architecture: 2-pass optimized (min/max scan + full statistics)")
    
    if ds_or_band is None:
        logger.error("Invalid dataset or band provided for statistics calculation.")
        return None
    
    try:
        # Get bands to process
        bands_to_process = []
        if isinstance(ds_or_band, gdal.Dataset):
            if ds_or_band.RasterCount == 0:
                logger.error("Provided dataset has no bands.")
                return None
            for i in range(1, ds_or_band.RasterCount + 1):
                bands_to_process.append(ds_or_band.GetRasterBand(i))
        else:
            bands_to_process.append(ds_or_band)
        
        # ====================================================================
        # PASS 1: Determine histogram bins + alpha detection + count alpha=0
        # ====================================================================
        logger.info("Pass 1/2: Min/max scan for histogram bins and alpha detection")
        logger.debug("Pass 1 scans for min/max values only (NOT full statistics)")
        band_ranges = {}
        alpha_band_idx = None
        alpha_characteristics = None
        alpha_0_count = 0
        
        # Find alpha band
        for idx, band in enumerate(bands_to_process):
            if not band:
                continue
            color_interp = gdal.GetColorInterpretationName(band.GetColorInterpretation())
            if color_interp == 'Alpha':
                alpha_band_idx = idx
                alpha_characteristics = AlphaCharacteristics()
                logger.debug(f"Found alpha band at index {idx}")
                break
        
        for band_idx, band in enumerate(bands_to_process):
            if not band:
                continue
            
            min_val, max_val = float('inf'), float('-inf')
            nodata_value = band.GetNoDataValue()
            
            # Handle multi-band NoData
            effective_nodata = nodata_value
            if nodata_value is not None and isinstance(ds_or_band, gdal.Dataset):
                nodata_values_str = str(nodata_value).split()
                if len(nodata_values_str) > 1 and len(nodata_values_str) == ds_or_band.RasterCount:
                    try:
                        effective_nodata = float(nodata_values_str[band_idx])
                    except (ValueError, IndexError) as e:
                        logger.warning(f"NoData value {nodata_value!r} could not be read as one number per band ({e}); using it as is")
                        effective_nodata = nodata_value
            
            # Scan blocks for min/max
            for block, x_off, y_off, x_sz, y_sz in _iterate_blocks(band, block_size):
                # If this is the alpha band, update characteristics and count alpha=0
                if band_idx == alpha_band_idx and alpha_characteristics is not None:
                    alpha_characteristics.update(block)
                    alpha_0_count += np.count_nonzero(block == 0)
                
                # Apply nodata mask in native dtype
                nodata_mask = _safe_nodata_comparison(block, effective_nodata, block.dtype)
                
                # Apply transparency mask if applicable
                mask_band = band.GetMaskBand()
                mask_flags = band.GetMaskFlags()
                if (not (mask_flags & gdal.GMF_NODATA) and
                    not (mask_flags & gdal.GMF_ALPHA) and
                    not (mask_flags & gdal.GMF_ALL_VALID)):
                    mask_block = mask_band.ReadAsArray(
                        xoff=x_off, yoff=y_off,
                        win_xsize=x_sz, win_ysize=y_sz
                    )
                    if mask_block is not None:
                        trans_mask = (mask_block == 0)
                        nodata_mask = nodata_mask | trans_mask
                
                # Apply alpha mask if alpha band exists and this is not the alpha band
                if alpha_band_idx is not None and band_idx != alpha_band_idx:
                    alpha_block = bands_to_process[alpha_band_idx].ReadAsArray(
                        xoff=x_off, yoff=y_off,
                        win_xsize=x_sz, win_ysize=y_sz
                    )
                    if alpha_block is not None:
                        alpha_mask = (alpha_block == 0)
                        nodata_mask = nodata_mask | alpha_mask
                
                # Get valid data
                valid_block = block[~nodata_mask]
                
                if valid_block.size > 0:
                    min_val = min(min_val, np.min(valid_block))
                    max_val = max(max_val, np.max(valid_block))
            
            # Create histogram bins
            if min_val == float('inf'):
                # No valid data found
                bins = np.linspace(0, 1, 2)
                min_val, max_val = 0, 1
            elif band.DataType == gdal.GDT_Byte:
                # Byte data: use 256 bins from 0 to 255
                bins = np.linspace(0, 255, 256)
            else:
                # Other data types: use 256 bins from min to max
                bins = np.linspace(min_val, max_val, 256)
            
            band_ranges[band_idx] = (min_val, max_val, bins)
            logger.debug(f"Band {band_idx + 1}: min={min_val:.6f}, max={max_val:.6f}")
        
        # Determine alpha handling strategy
        alpha_type = 'binary'  # Default
        alpha_tolerance = 0
        use_alpha_as_mask_only = True
        
        if alpha_characteristics:
            # Get thresholds from config
            binary_threshold = config.get("statistics.alpha_binary_threshold", 0.999)
            near_binary_threshold = config.get("statistics.alpha_near_binary_threshold", 0.99)
            
            alpha_type = alpha_characteristics.get_alpha_type(
                binary_threshold=binary_threshold,
                near_binary_threshold=near_binary_threshold
            )
            
            binary_percent = ((alpha_characteristics.zero_count + alpha_characteristics.max_count) /
                            alpha_characteristics.total_count * 100 if alpha_characteristics.total_count > 0 else 0)
            
            logger.info(f"Alpha band type detected: {alpha_type}")
            logger.debug(f"  - Binary pixels: {binary_percent:.2f}%")
            logger.debug(f"  - Unique values: {len(alpha_characteristics.unique_values)}")
            logger.debug(f"  - Alpha=0 count: {alpha_0_count:,}")
            
            # Configure alpha handling
            if alpha_type == 'binary':
                use_alpha_as_mask_only = True
                alpha_tolerance = 0
                logger.info("Alpha band will be used as binary transparency mask")
            
            elif alpha_type == 'near_binary':
                use_alpha_as_mask_only = config.get("statistics.treat_near_binary_as_mask", True)
                alpha_tolerance = alpha_characteristics.get_artifact_tolerance()
                if use_alpha_as_mask_only:
                    logger.info(f"Alpha band has artifacts; using tolerance={alpha_tolerance}")
                else:
                    logger.info("Alpha band treated as data (near-binary, full statistics)")
            
            else:  # graduated
                use_alpha_as_mask_only = False
                alpha_tolerance = 0
                logger.info("Alpha band contains graduated values; calculating full statistics")
        
        # ====================================================================
        # PASS 2: Accumulate statistics with alpha/transparency mask caching
        # ====================================================================
        logger.info("Pass 2/2: Calculating statistics, histogram, and PAM (combined pass)")
        logger.debug("Pass 2 processes statistics + histogram + PAM in one pass with mask caching")
        bands_stats = []
        
        # Initialize band accumulators
        band_accumulators = {}
        for band_idx, band in enumerate(bands_to_process):
            if not band:
                continue
            
            nodata_value = band.GetNoDataValue()
            effective_nodata = nodata_value
            if nodata_value is not None and isinstance(ds_or_band, gdal.Dataset):
                nodata_values_str = str(nodata_value).split()
                if len(nodata_values_str) > 1 and len(nodata_values_str) == ds_or_band.RasterCount:
                    try:
                        effective_nodata = float(nodata_values_str[band_idx])
                    except (ValueError, IndexError) as e:
                        logger.warning(f"NoData value {nodata_value!r} could not be read as one number per band ({e}); using it as is")
                        effective_nodata = nodata_value
            
            color_interp = gdal.GetColorInterpretationName(band.GetColorInterpretation())
            is_alpha_band = (color_interp == 'Alpha')
            
            band_desc = band.GetDescription()
            if band_desc:
                band_name = band_desc
            elif color_interp:
                band_name = color_interp
            else:
                band_name = f"Band {band_idx + 1}"
            
            band_accumulators[band_idx] = {
                'stats': OnlineStatistics(),
                'histogram': OnlineHistogram(band_ranges[band_idx][2]),
                'hist_stats': OnlineStatistics(),
                'hist_histogram': OnlineHistogram(band_ranges[band_idx][2]),
                'nodata_count': 0,
                'mask_count': 0,
                'nodata_value': nodata_value,
                'effective_nodata': effective_nodata,
                'is_alpha_band': is_alpha_band,
                'band_name': band_name,
                'color_interp': color_interp
            }
        
        # Iterate over block positions (not individual bands)
        # This enables caching of alpha and transparency masks
        block_height, block_width = block_size
        first_band = bands_to_process[0]
        band_width = first_band.XSize
        band_height = first_band.YSize
        total_pixels = band_width * band_height
        
        for y_offset in range(0, band_height, block_height):
            y_size = min(block_height, band_height - y_offset)
            
            for x_offset in range(0, band_width, block_width):
                x_size = min(block_width, band_width - x_offset)
                
                # ===== CACHE ALPHA BLOCK (Read once, reuse for all bands) =====
                alpha_block_cached = None
                alpha_mask_cached = None
                if alpha_band_idx is not None and config.get("statistics.cache_alpha_blocks", True):
                    alpha_band = bands_to_process[alpha_band_idx]
                    alpha_block_cached = alpha_band.ReadAsArray(
                        xoff=x_offset, yoff=y_offset,
                        win_xsize=x_size, win_ysize=y_size
                    )
                    if alpha_block_cached is not None:
                        alpha_dtype = _get_optimal_dtype(alpha_band)
                        alpha_block_cached = alpha_block_cached.astype(alpha_dtype)
                        
                        # Apply tolerance if configured
                        if alpha_tolerance > 0:
                            alpha_mask_cached = (alpha_block_cached <= alpha_tolerance)
                        else:
                            alpha_mask_cached = (alpha_block_cached == 0)
                
                # ===== CACHE TRANSPARENCY MASK (Read once, reuse for all bands) =====
                transparency_mask_cached = None
                if config.get("statistics.cache_transparency_masks", True):
                    # Check first band to determine if transparency mask is used
                    mask_band = first_band.GetMaskBand()
                    mask_flags = first_band.GetMaskFlags()
                    
                    # Only read mask if it's a real mask (not derived from nodata/alpha)
                    if (not (mask_flags & gdal.GMF_NODATA) and
                        not (mask_flags & gdal.GMF_ALPHA) and
                        not (mask_flags & gdal.GMF_ALL_VALID)):
                        
                        mask_block = mask_band.ReadAsArray(
                            xoff=x_offset, yoff=y_offset,
                            win_xsize=x_size, win_ysize=y_size
                        )
                        if mask_block is not None:
                            transparency_mask_cached = (mask_block == 0)
                
                # ===== PROCESS ALL BANDS AT THIS BLOCK POSITION =====
                for band_idx, band in enumerate(bands_to_process):
                    if not band:
                        continue
                    
                    acc = band_accumulators[band_idx]
                    
                    # Read band block
                    block = band.ReadAsArray(
                        xoff=x_offset, yoff=y_offset,
                        win_xsize=x_size, win_ysize=y_size
                    )
                    
                    if block is None:
                        logger.warning(f"Failed to read block at ({x_offset}, {y_offset}) for band {band_idx + 1}")
                        continue
                    
                    block_dtype = _get_optimal_dtype(band)
                    block = block.astype(block_dtype)
                    
                    # Apply nodata mask
                    nodata_mask = _safe_nodata_comparison(block, acc['effective_nodata'], block_dtype)
                    acc['nodata_count'] += np.count_nonzero(nodata_mask)
                    
                    # Reuse cached transparency mask
                    trans_mask = transparency_mask_cached if transparency_mask_cached is not None else np.zeros_like(block, dtype=bool)
                    if transparency_mask_cached is not None:
                        acc['mask_count'] += np.count_nonzero(trans_mask)
                    
                    # Reuse cached alpha mask (skip for alpha band itself)
                    alpha_mask = alpha_mask_cached if (alpha_mask_cached is not None and band_idx != alpha_band_idx) else np.zeros_like(block, dtype=bool)
                    
                    # Combine masks
                    invalid_mask = nodata_mask | trans_mask | alpha_mask
                    valid_block = block[~invalid_mask]
                    
                    # Filter infinite values for float types
                    if valid_block.size > 0 and 'Float' in gdal.GetDataTypeName(band.DataType):
                        finite_mask = np.isfinite(valid_block)
                        valid_block = valid_block[finite_mask]
                    
                    if valid_block.size > 0:
                        # Promote to float64 for statistics
                        valid_block_f64 = _promote_for_statistics(valid_block)
                        acc['stats'].update(valid_block_f64)
                        acc['histogram'].update(valid_block_f64)
                    
                    # For histogram visualization: handle alpha band differently
                    if acc['is_alpha_band']:
                        # Alpha band: use data excluding only nodata and trans_mask
                        hist_mask = nodata_mask | trans_mask
                        hist_block = block[~hist_mask]
                        if hist_block.size > 0:
                            hist_block_f64 = _promote_for_statistics(hist_block)
                            acc['hist_stats'].update(hist_block_f64)
                            acc['hist_histogram'].update(hist_block_f64)
        
        # ===== FINALIZE STATISTICS FOR ALL BANDS =====
        for band_idx, band in enumerate(bands_to_process):
            if not band or band_idx not in band_accumulators:
                continue
            
            acc = band_accumulators[band_idx]
            
            # Finalize statistics
            final_stats = acc['stats'].finalize()
            hist_counts, hist_bins = acc['histogram'].get_result()
            
            # For alpha bands, use hist_histogram for visualization
            if acc['is_alpha_band']:
                hist_counts, hist_bins = acc['hist_histogram'].get_result()
            
            # Generate PAM histogram dict immediately
            pam_histogram_dict = None
            if final_stats['count'] > 0:
                pam_histogram_dict = {
                    "HistMin": band_ranges[band_idx][0],
                    "HistMax": band_ranges[band_idx][1],
                    "BucketCount": len(hist_counts),
                    "HistCounts": '|'.join(map(str, hist_counts))
                }
            
            # Create StatisticsBand object
            bands_stats.append(StatisticsBand(
                band_name=acc['band_name'],
                valid_percent=(final_stats['count'] / total_pixels) * 100 if total_pixels > 0 else 0.0,
                valid_count=final_stats['count'],
                mask_count=int(acc['mask_count']),
                alpha_0_count=int(alpha_0_count) if alpha_band_idx is not None else 0,
                nodata_count=int(acc['nodata_count']),
                nodata_value=acc['nodata_value'],
                minimum=final_stats['minimum'],
                maximum=final_stats['maximum'],
                mean=final_stats['mean'],
                std_dev=final_stats['std_dev'],
                histogram_counts=hist_counts,
                histogram_bins=hist_bins,
                histogram=pam_histogram_dict
            ))
            
            logger.debug(f"Band {band_idx + 1} ({acc['band_name']}): {final_stats['count']:,} valid pixels")
        
        if not bands_stats:
            logger.warning("Block-based statistics calculation resulted in no data.")
            return None
        
        logger.info("Block-based statistics calculation completed successfully")
        return bands_stats
    
    except Exception as e:
        logger.error(f"Error during block-based statistics calculation: {e}", exc_info=True)
        return None


def _calculate_statistics_full(ds_or_band: Union[gdal.Dataset, gdal.Band]) -> Optional[List[StatisticsBand]]:
    """
    Fast single-pass statistics calculation using native data types.

    This function loads the entire raster into memory for processing, making it
    very fast for files that fit comfortably in RAM. Uses native data types
    (Byte, UInt16, Float32) for 50-87% memory reduction compared to always
    using float64.
    
    Args:
        ds_or_band: GDAL Dataset or Band to calculate statistics for
        
    Returns:
        List of StatisticsBand objects, one per band, or None if calculation fails
        
    Note:
        This is the "fast path" that should be used for most files.
        Large files exceeding memory threshold will use _calculate_statistics_blocked().
    """
    logger.debug("Using fast path: calculating statistics with full image load...")
    if ds_or_band is None:
        logger.error("Invalid dataset or band provided for statistics calculation.")
        return None

    bands_stats: List[StatisticsBand] = []

    try:
        bands_to_process = []
        if isinstance(ds_or_band, gdal.Dataset):
            if ds_or_band.RasterCount == 0:
                logger.error("Provided dataset has no bands.")
                return None
            for i in range(1, ds_or_band.RasterCount + 1):
                bands_to_process.append(ds_or_band.GetRasterBand(i))
        else:
            # It's a single band object
            bands_to_process.append(ds_or_band)

        # --- Alpha=0 Count ---
        # If there is an alpha band, count the values where alpha=0 (transparent)
        # Use native dtype for memory efficiency instead of numpy default float64
        alpha_0_count = 0
        alpha_mask = np.zeros(bands_to_process[0].ReadAsArray().shape, dtype=bool)
        for band in bands_to_process:
            if not band:
                continue
            optimal_dtype = _get_optimal_dtype(band)
            data = band.ReadAsArray().astype(optimal_dtype)
            color_interp = gdal.GetColorInterpretationName(band.GetColorInterpretation())
            if color_interp == 'Alpha':
                alpha_mask = (data == 0)
                alpha_0_count = np.count_nonzero(alpha_mask)

        for i, band in enumerate(bands_to_process, 1):
            if not band:
                continue

            optimal_dtype = _get_optimal_dtype(band)
            data = band.ReadAsArray().astype(optimal_dtype)
            color_interp = gdal.GetColorInterpretationName(band.GetColorInterpretation())
            
            # Initialize counts
            nodata_count = 0
            trans_count = 0

            # --- NoData Count ---
            # Use dtype-aware nodata comparison
            nodata_value = band.GetNoDataValue()
            
            # Handle multi-band NoData where the value is a space-separated string
            effective_nodata = nodata_value
            if nodata_value is not None:
                nodata_values_str = str(nodata_value).split()
                if isinstance(ds_or_band, gdal.Dataset) and len(nodata_values_str) > 1 and len(nodata_values_str) == ds_or_band.RasterCount:
                    try:
                        effective_nodata = float(nodata_values_str[i-1])
                    except (ValueError, IndexError) as e:
                        logger.warning(f"NoData value {nodata_value!r} could not be read as one number per band ({e}); using it as is")
                        effective_nodata = nodata_value
            
            # Use safe nodata comparison with dtype awareness
            nodata_mask = _safe_nodata_comparison(data, effective_nodata, optimal_dtype)
            
            nodata_count = np.count_nonzero(nodata_mask)

            # --- Transparency Mask Count ---
            trans_mask = np.zeros_like(data, dtype=bool)
            mask_band = band.GetMaskBand()
            mask_flags = band.GetMaskFlags()
            
            if (not (mask_flags & gdal.GMF_NODATA) and
                not (mask_flags & gdal.GMF_ALPHA) and
                not (mask_flags & gdal.GMF_ALL_VALID)):
                mask_data = mask_band.ReadAsArray()
                trans_mask = (mask_data == 0)
            
            trans_count = np.count_nonzero(trans_mask)

            # --- Valid Data Calculation ---
            # The alpha mask applies to the colour bands, not to the alpha band itself: its
            # own statistics cover every pixel it holds, zeros included, as its histogram
            # below already did and as the blocked path has always done. Masking the alpha
            # band with itself gave a binary alpha a minimum of 255 and a spread of zero.
            is_alpha_band = color_interp == 'Alpha'
            invalid_mask = nodata_mask | trans_mask
            if not is_alpha_band:
                invalid_mask = invalid_mask | alpha_mask
            valid_data = data[~invalid_mask]

            # Ensure infinite values are excluded from valid_data to prevent statistics crashes
            if valid_data.size > 0 and 'Float' in gdal.GetDataTypeName(band.DataType):
                finite_mask = np.isfinite(valid_data)
                if not np.all(finite_mask):
                    # Only filter if we actually found non-finite values
                    valid_data = valid_data[finite_mask]

            if valid_data.size == 0:
                logger.warning(f"Band {i} contains no valid data after masking and infinite value filtering.")
            
            # Determine band name
            band_name = None
            band_desc = band.GetDescription()
            if band_desc:
                band_name = band_desc
            elif color_interp:
                band_name = color_interp
            else:
                band_name = f"Band {i}"
    
            # Calculate histogram bins and counts for visualization
            # For alpha bands: show ALL pixels (including alpha=0) to display the full distribution
            # For RGB bands: show only valid pixels (excluding alpha=0)
            hist_counts, hist_bins = None, None
            pam_histogram_data = None
            
            if is_alpha_band:
                # Alpha band: use data excluding only nodata and transparency mask (not alpha_mask)
                alpha_histogram_mask = nodata_mask | trans_mask
                alpha_histogram_data = data[~alpha_histogram_mask]
                if alpha_histogram_data.size > 0:
                    hist_counts, hist_bins = _calculate_histogram_bins(alpha_histogram_data, band)
                    pam_histogram_data = alpha_histogram_data
            else:
                # RGB bands: use valid_data (excludes nodata, trans_mask, and alpha_mask)
                if valid_data.size > 0:
                    hist_counts, hist_bins = _calculate_histogram_bins(valid_data, band)
                    pam_histogram_data = valid_data
            
            # Promote to float64 for accurate statistics calculation
            # This happens AFTER masking, so we only promote the valid pixels
            valid_data_f64 = _promote_for_statistics(valid_data) if valid_data.size > 0 else valid_data
            
            # Generate PAM histogram immediately to avoid storing raw pixel arrays
            # This prevents memory issues with large files
            pam_histogram_dict = None
            if pam_histogram_data is not None and pam_histogram_data.size > 0:
                pam_histogram_dict = _get_pam_histogram(band, pam_histogram_data)
            
            # Create StatisticsBand object
            bands_stats.append(StatisticsBand(
                band_name=band_name,
                valid_percent=(valid_data.size / data.size) * 100 if data.size > 0 else 0.0,
                valid_count=valid_data.size,
                mask_count=int(trans_count),
                alpha_0_count=int(alpha_0_count),
                nodata_count=int(nodata_count),
                nodata_value=nodata_value,
                minimum=float(np.min(valid_data_f64)) if valid_data.size > 0 else None,
                maximum=float(np.max(valid_data_f64)) if valid_data.size > 0 else None,
                mean=float(np.mean(valid_data_f64)) if valid_data.size > 0 else None,
                std_dev=float(np.std(valid_data_f64)) if valid_data.size > 0 else None,
                histogram_counts=hist_counts,
                histogram_bins=hist_bins,
                histogram=pam_histogram_dict  # Store PAM histogram dict instead of raw pixels
            ))

        if not bands_stats:
            logger.warning("Statistics calculation resulted in no data.")
            return None
            
        return bands_stats

    except Exception as e:
        logger.error(f"An unexpected error occurred during statistics calculation: {e}", exc_info=True)
        return None


def calculate_statistics(
    ds_or_band: Union[gdal.Dataset, gdal.Band],
    max_pixels: Optional[int] = None,
    block_size: Tuple[int, int] = DEFAULT_BLOCK_SIZE
) -> Optional[List[StatisticsBand]]:
    """
    Calculate comprehensive raster statistics with automatic strategy selection.
    
    This function automatically chooses between:
    - **Fast path**: Single-pass for files ≤ max_pixels (default: 268M = 16,384²)
    - **Blocked path**: Two-pass for files > max_pixels
    
    The fast path loads the entire image into memory using native data types
    (Byte, UInt16, Float32) for optimal performance. The blocked path processes
    large files in chunks to avoid memory overflow.
    
    Strategy Selection:
        1. Check configuration for max_pixels_fast_path setting
        2. If not set, auto-detect threshold based on available RAM (requires psutil)
        3. Compare total_pixels to threshold
        4. Route to _calculate_statistics_full() or _calculate_statistics_blocked()
    
    Args:
        ds_or_band: GDAL Dataset or Band to calculate statistics for
        max_pixels: Threshold for blocking (None = auto-detect from config/RAM)
        block_size: Block dimensions for blocked path (height, width)
                    Default: (4096, 4096) = 16.7MP blocks (safe for 16GB RAM)
        
    Returns:
        List of StatisticsBand objects, one per band, or None if calculation fails
        
    Configuration:
        Add to config.toml to customize behavior:
        ```toml
        [statistics]
        max_pixels_fast_path = 268435456  # 16,384² pixels
        block_size = [2048, 2048]
        force_strategy = "auto"  # "fast", "blocked", or "auto"
        ```
    
    Examples:
        >>> from osgeo import gdal
        >>> dataset = gdal.Open('example.tif')

        >>> # Automatic strategy selection
        >>> stats = calculate_statistics(dataset)
        >>> f"{stats[0].minimum} to {stats[0].maximum}, mean {stats[0].mean}"
        '100.0 to 200.0, mean 150.0'

        >>> # Force the fast path by raising the pixel-count threshold
        >>> stats = calculate_statistics(dataset, max_pixels=100_000_000)

        >>> # Custom block size for the blocked path
        >>> stats = calculate_statistics(dataset, max_pixels=1, block_size=(32, 32))
    """
    if ds_or_band is None:
        logger.error("Invalid dataset or band provided for statistics calculation.")
        return None
    
    # Check for forced strategy in config (empty string or "auto" means auto-select)
    force_strategy = config.get("statistics.force_strategy", "auto")
    if force_strategy and force_strategy != "auto":
        if force_strategy == "fast":
            logger.info("Using fast path (forced by configuration)")
            return _calculate_statistics_full(ds_or_band)
        elif force_strategy == "blocked":
            logger.info("Using blocked path (forced by configuration)")
            return _calculate_statistics_blocked(ds_or_band, block_size)
        else:
            logger.warning(f"Invalid force_strategy '{force_strategy}' in config, using auto-selection")
    
    # Get band for size check
    if isinstance(ds_or_band, gdal.Dataset):
        if ds_or_band.RasterCount == 0:
            logger.error("Provided dataset has no bands.")
            return None
        band = ds_or_band.GetRasterBand(1)
    else:
        band = ds_or_band
    
    # Get dimensions
    width = band.XSize
    height = band.YSize
    total_pixels = width * height
    
    # Determine threshold
    if max_pixels is None:
        # Check config for block_size override
        config_block_size = config.get("statistics.block_size", None)
        if config_block_size is not None and isinstance(config_block_size, list):
            block_size = tuple(config_block_size)
            logger.debug(f"Using block_size from config: {block_size}")
        
        # Calculate or get threshold
        max_pixels = _calculate_max_pixels_threshold()
    
    # Log strategy decision
    logger.info(f"Image dimensions: {width:,} x {height:,} = {total_pixels:,} pixels")

    if total_pixels <= max_pixels:
        logger.info(f"Using fast path: {total_pixels:,} pixels <= {max_pixels:,} threshold")
        logger.debug("Strategy: Single-pass with native dtype optimization")
        return _calculate_statistics_full(ds_or_band)
    else:
        logger.info(f"Using blocked path: {total_pixels:,} pixels > {max_pixels:,} threshold")
        block_pixels = block_size[0] * block_size[1]
        logger.debug(f"Strategy: Two-pass block processing with {block_size[0]}x{block_size[1]} blocks ({block_pixels:,} pixels per block)")
        return _calculate_statistics_blocked(ds_or_band, block_size)
