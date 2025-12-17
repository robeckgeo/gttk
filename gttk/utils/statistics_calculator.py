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
Statistics Calculator.

A comprehensive module to calculate raster statistics for GDAL datasets,
including sophisticated transparency mask detection, comprehensive statistics,
and PAM (Persistent Auxiliary Metadata) XML generation.

This module is designed to be independent of matplotlib to ensure it can run
in environments where matplotlib may cause conflicts, such as ArcGIS Pro.
The histogram visualization is handled separately by generate_histogram.py.
"""

import numpy as np
from osgeo import gdal
import logging
import xml.etree.ElementTree as ET
from xml.dom import minidom
from typing import Optional, Union, List
from gttk.utils.data_models import StatisticsBand

# Configure logging
logger = logging.getLogger(__name__)

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

def _get_pam_histogram(band: gdal.Band, valid_data: np.ndarray) -> dict:
    """Calculates a histogram suitable for Esri's PAM XML format."""
    # Safety check: ensure valid_data is not empty
    if valid_data.size == 0:
        logger.warning("Cannot generate PAM histogram: valid_data array is empty")
        return {
            "HistMin": 0,
            "HistMax": 1,
            "BucketCount": 1,
            "HistCounts": "0"
        }
    
    data_type = band.DataType
    gdal_type_name = gdal.GetDataTypeName(data_type)
    
    if 'Byte' in gdal_type_name:
        # For 8-bit data, create 256 bins with precise edges from 0 to 256.
        # This ensures the histogram visually covers the exact data range [0, 255].
        hist_min, hist_max, n_bins = 0, 256, 256
    else:
        min_val, max_val = np.min(valid_data), np.max(valid_data)
        if 'UInt' in gdal_type_name:
            # Bins from 0 to max for unsigned integers
            hist_min, hist_max = -0.5, max_val + 0.5
            n_bins = int(min((max_val - min_val), 256)) # Cap bins for large integer ranges
        else:
            # General case for float or signed integers
            hist_min, hist_max = min_val, max_val
            n_bins = 256 # Default number of bins for float/signed
            
    if hist_max <= hist_min: # Handle cases with single value data
        hist_max = hist_min + 1
        n_bins = 1

    bins = np.linspace(hist_min, hist_max, n_bins + 1)
    counts, _ = np.histogram(valid_data, bins=bins)
    
    return {
        "HistMin": hist_min,
        "HistMax": hist_max,
        "BucketCount": n_bins,
        "HistCounts": '|'.join(map(str, counts.tolist()))
    }

def write_pam_xml(filename: str, pam_data: dict):
    """Writes the PAM statistics to an .aux.xml file."""
    if not pam_data:
        return

    root = ET.Element('PAMDataset')
    for band_index, band_stats in pam_data.items():
        band_elem = ET.SubElement(root, 'PAMRasterBand', band=str(band_index))

        if band_stats.get('description'):
            ET.SubElement(band_elem, 'Description').text = band_stats['description']

        if band_stats.get('nodata_value') is not None:
            ET.SubElement(band_elem, 'NoDataValue').text = str(band_stats['nodata_value'])
        
        if 'histogram' in band_stats:
            hist_data = band_stats['histogram']
            histograms_elem = ET.SubElement(band_elem, 'Histograms')
            hist_item_elem = ET.SubElement(histograms_elem, 'HistItem')
            ET.SubElement(hist_item_elem, 'HistMin').text = str(hist_data['HistMin'])
            ET.SubElement(hist_item_elem, 'HistMax').text = str(hist_data['HistMax'])
            ET.SubElement(hist_item_elem, 'BucketCount').text = str(hist_data['BucketCount'])
            ET.SubElement(hist_item_elem, 'IncludeOutOfRange').text = '1'
            ET.SubElement(hist_item_elem, 'Approximate').text = '0'
            ET.SubElement(hist_item_elem, 'HistCounts').text = hist_data['HistCounts']

        if 'stats' in band_stats:
            stats_data = band_stats['stats']
            metadata_elem = ET.SubElement(band_elem, 'Metadata')
            stat_map = {
                'Minimum': 'STATISTICS_MINIMUM', 'Maximum': 'STATISTICS_MAXIMUM',
                'Mean': 'STATISTICS_MEAN', 'Std Dev': 'STATISTICS_STDDEV',
                'Median': 'STATISTICS_MEDIAN', 'Valid Count': 'STATISTICS_COUNT'
            }
            for key, mdi_key in stat_map.items():
                if key in stats_data:
                    ET.SubElement(metadata_elem, 'MDI', key=mdi_key).text = str(stats_data[key])
            
            ET.SubElement(metadata_elem, 'MDI', key='STATISTICS_SKIPFACTORX').text = '1'
            ET.SubElement(metadata_elem, 'MDI', key='STATISTICS_SKIPFACTORY').text = '1'
            ET.SubElement(metadata_elem, 'MDI', key='STATISTICS_EXCLUDEDVALUES')

            if 'color_interp' in band_stats:
                ET.SubElement(metadata_elem, 'MDI', key='ColorInterp').text = band_stats['color_interp']

    xml_str = ET.tostring(root, 'unicode')
    reparsed = minidom.parseString(xml_str)
    pretty_xml = reparsed.toprettyxml(indent="  ")
    pretty_xml_no_decl = '\n'.join(pretty_xml.split('\n')[1:])

    pam_filename = filename + '.aux.xml'
    try:
        with open(pam_filename, 'w', encoding='utf-8') as f:
            f.write(pretty_xml_no_decl)
        logger.info(f"Successfully wrote statistics to {pam_filename}")
    except IOError as e:
        logger.error(f"Failed to write .aux.xml file: {e}")

def calculate_statistics(ds_or_band: Union[gdal.Dataset, gdal.Band]) -> Optional[List[StatisticsBand]]:
    """
    Calculates comprehensive statistics for a raster dataset or a single band.
    
    Returns a list of StatisticsBand objects with all statistics populated including
    histogram data stored as a list for later visualization.
    
    Args:
        ds_or_band: GDAL Dataset or Band to calculate statistics for
        
    Returns:
        List of StatisticsBand objects, one per band, or None if calculation fails
    """
    logger.debug("Calculating statistics...")
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
        alpha_0_count = 0
        alpha_mask = np.zeros(bands_to_process[0].ReadAsArray().shape, dtype=bool)
        for band in bands_to_process:
            if not band:
                continue
            data = band.ReadAsArray().astype(np.float32)
            color_interp = gdal.GetColorInterpretationName(band.GetColorInterpretation())
            if color_interp == 'Alpha':
                alpha_mask = (data == 0)
                alpha_0_count = np.count_nonzero(alpha_mask)

        for i, band in enumerate(bands_to_process, 1):
            if not band:
                continue

            # Read as float64 to avoid overflow with extreme NoData values
            data = band.ReadAsArray().astype(np.float64)
            color_interp = gdal.GetColorInterpretationName(band.GetColorInterpretation())
            
            # Initialize counts
            nodata_count = 0
            trans_count = 0

            # --- NoData Count ---
            nodata_value = band.GetNoDataValue()
            nodata_mask = np.zeros_like(data, dtype=bool)
            
            if nodata_value is not None:
                # Handle multi-band NoData where the value is a space-separated string
                nodata_values_str = str(nodata_value).split()
                if isinstance(ds_or_band, gdal.Dataset) and len(nodata_values_str) > 1 and len(nodata_values_str) == ds_or_band.RasterCount:
                    try:
                        band_nodata = float(nodata_values_str[i-1])
                        if np.isnan(band_nodata):
                            nodata_mask = np.isnan(data)
                        else:
                            # Always include NaN pixels in addition to metadata nodata value
                            nodata_mask = (data == band_nodata) | np.isnan(data)
                    except (ValueError, IndexError):
                        # Fallback: at least include NaN pixels
                        nodata_mask = np.isnan(data)
                else:
                    # Standard single nodata value handling
                    if np.isnan(nodata_value):
                        nodata_mask = np.isnan(data)
                    else:
                        # Always include NaN pixels in addition to metadata nodata value
                        nodata_mask = (data == nodata_value) | np.isnan(data)
            else:
                # No nodata metadata, but still include NaN pixels
                nodata_mask = np.isnan(data)
            
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
            invalid_mask = nodata_mask | trans_mask | alpha_mask
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
            is_alpha_band = color_interp == 'Alpha'
            
            hist_counts, hist_bins = None, None
            if is_alpha_band:
                # Alpha band: use data excluding only nodata and transparency mask (not alpha_mask)
                alpha_histogram_mask = nodata_mask | trans_mask
                alpha_histogram_data = data[~alpha_histogram_mask]
                if alpha_histogram_data.size > 0:
                    hist_counts, hist_bins = _calculate_histogram_bins(alpha_histogram_data, band)
            else:
                # RGB bands: use valid_data (excludes nodata, trans_mask, and alpha_mask)
                if valid_data.size > 0:
                    hist_counts, hist_bins = _calculate_histogram_bins(valid_data, band)
            
            # Create StatisticsBand object
            bands_stats.append(StatisticsBand(
                band_name=band_name,
                valid_percent=(valid_data.size / data.size) * 100 if data.size > 0 else 0.0,
                valid_count=valid_data.size,
                mask_count=int(trans_count),
                alpha_0_count=int(alpha_0_count),
                nodata_count=int(nodata_count),
                nodata_value=nodata_value,
                minimum=float(np.min(valid_data)) if valid_data.size > 0 else None,
                maximum=float(np.max(valid_data)) if valid_data.size > 0 else None,
                mean=float(np.mean(valid_data)) if valid_data.size > 0 else None,
                std_dev=float(np.std(valid_data)) if valid_data.size > 0 else None,
                median=float(np.median(valid_data)) if valid_data.size > 0 else None,
                histogram_counts=hist_counts,
                histogram_bins=hist_bins,
                histogram=valid_data if valid_data.size > 0 else None  # Keep numpy array for PAM
            ))

        if not bands_stats:
            logger.warning("Statistics calculation resulted in no data.")
            return None
            
        return bands_stats

    except Exception as e:
        logger.error(f"An unexpected error occurred during statistics calculation: {e}", exc_info=True)
        return None


def build_pam_data_from_stats(bands: List[StatisticsBand], ds_or_band: Union[gdal.Dataset, gdal.Band]) -> dict:
    """
    Build PAM XML data structure from StatisticsBand objects.
    
    Converts modern StatisticsBand dataclasses to legacy dict format for PAM XML export.
    
    Args:
        bands: List of StatisticsBand objects with statistics
        ds_or_band: GDAL Dataset or Band to get band metadata from
        
    Returns:
        Dictionary containing PAM data structure for XML export
    """
    pam_data = {}
    
    # Get band objects
    bands_to_process = []
    if isinstance(ds_or_band, gdal.Dataset):
        for i in range(1, ds_or_band.RasterCount + 1):
            bands_to_process.append(ds_or_band.GetRasterBand(i))
    else:
        bands_to_process.append(ds_or_band)
    
    for i, (band_stats, band_obj) in enumerate(zip(bands, bands_to_process), 1):
        if not band_obj:
            continue
            
        pam_entry = {
            "stats": {
                "Valid Count": band_stats.valid_count,
                "Minimum": band_stats.minimum,
                "Maximum": band_stats.maximum,
                "Mean": band_stats.mean,
                "Std Dev": band_stats.std_dev,
                "Median": band_stats.median
            },
            "color_interp": gdal.GetColorInterpretationName(band_obj.GetColorInterpretation()),
            "nodata_value": band_stats.nodata_value,
            "description": band_obj.GetDescription()
        }
        
        # Generate PAM histogram if raw pixel data exists
        if band_stats.histogram is not None and hasattr(band_stats.histogram, 'size'):
            # histogram field contains numpy array for PAM export
            pam_histogram = _get_pam_histogram(band_obj, band_stats.histogram)
            pam_entry["histogram"] = pam_histogram
        
        pam_data[i] = pam_entry
    
    return pam_data