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
PAM (Persistent Auxiliary Metadata) XML Writer.

Functions for generating and writing PAM XML files (.aux.xml) with statistics
and histogram data in Esri's PAM format.

Functions:
    _get_pam_histogram: Generate PAM histogram dict from valid data
    write_pam_xml: Write PAM XML to .aux.xml file
    build_pam_data_from_stats: Convert StatisticsBand to PAM format
"""

import logging
import xml.etree.ElementTree as ET
from xml.dom import minidom
from typing import Union, List
from osgeo import gdal
import numpy as np

from gttk.utils.data_models import StatisticsBand

# Configure logging
logger = logging.getLogger(__name__)


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
            
        # Build stats dict, only including median if it exists
        stats_dict = {
            "Valid Count": band_stats.valid_count,
            "Minimum": band_stats.minimum,
            "Maximum": band_stats.maximum,
            "Mean": band_stats.mean,
            "Std Dev": band_stats.std_dev,
        }
        
        # Only include median if it's not None
        if band_stats.median is not None:
            stats_dict["Median"] = band_stats.median
        
        pam_entry = {
            "stats": stats_dict,
            "color_interp": gdal.GetColorInterpretationName(band_obj.GetColorInterpretation()),
            "nodata_value": band_stats.nodata_value,
            "description": band_obj.GetDescription()
        }
        
        # Add PAM histogram if it was generated
        if band_stats.histogram is not None:
            if isinstance(band_stats.histogram, dict):
                # histogram field already contains PAM histogram dict
                pam_entry["histogram"] = band_stats.histogram
            elif hasattr(band_stats.histogram, 'size'):
                # Legacy: histogram field contains numpy array
                pam_histogram = _get_pam_histogram(band_obj, band_stats.histogram)
                pam_entry["histogram"] = pam_histogram
        
        pam_data[i] = pam_entry
    
    return pam_data
