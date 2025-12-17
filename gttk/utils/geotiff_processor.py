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
Core GeoTIFF Processing and Analysis Utilities.

This module provides a suite of low-level functions for interacting with GeoTIFF
files using GDAL. It serves as the primary interface for extracting metadata,
calculating metrics like compression efficiency, handling NoData values, and
managing transparency masks.
"""
import re
import logging
import numpy as np
import tifffile
from decimal import Decimal, DecimalException, getcontext
from osgeo import gdal, osr
from typing import Any, Optional, Dict, List, Tuple, Union
from gttk.utils.data_models import GeoTiffInfo
from gttk.utils.srs_logic import get_vertical_srs
from gttk.utils.tiff_tag_parser import TiffTagParser

LERC_PARAMS_TAG_CODE = 50674

logger = logging.getLogger(__name__)

def _retrieve_projection_info(ds: gdal.Dataset, srs: osr.SpatialReference) -> Dict[str, Any]:
    """
    Extract RAW projection information without formatting.
    
    This replaces geokey_parser.get_projection_info() by extracting data once
    and storing it in raw form for later formatting by renderers.
    
    Args:
        ds: GDAL dataset
        srs: Spatial reference system from dataset
        
    Returns:
        Dictionary with raw projection information (names and codes separate)
    """
    info = {}
    
    if not srs:
        return info
    
    # Raster type (PixelIsArea or PixelIsPoint)
    metadata = ds.GetMetadata()
    raster_type = metadata.get('AREA_OR_POINT', 'Area').lower()
    info['raster_type'] = 'PixelIsArea' if raster_type == 'area' else 'PixelIsPoint'
    
    # CS types
    info['is_geographic'] = srs.IsGeographic()
    info['is_projected'] = srs.IsProjected()
    info['is_compound'] = srs.IsCompound()
    
    # Geographic CS (store name and code separately)
    if srs.IsGeographic() or srs.IsProjected():
        try:
            info['geographic_cs_name'] = srs.GetAttrValue('GEOGCS')
            info['geographic_cs_code'] = srs.GetAuthorityCode('GEOGCS')
            info['datum_name'] = srs.GetAttrValue('DATUM')
            info['datum_code'] = srs.GetAuthorityCode('DATUM')
            info['ellipsoid_name'] = srs.GetAttrValue('SPHEROID')
            info['semi_major'] = srs.GetSemiMajor()
            info['inv_flattening'] = srs.GetInvFlattening()
            info['angular_unit_name'] = srs.GetAngularUnitsName()
        except Exception as e:
            logger.debug(f"Error extracting geographic info: {e}")
    
    # Projected CS
    if srs.IsProjected():
        try:
            info['projected_cs_name'] = srs.GetAttrValue('PROJCS')
            info['projected_cs_code'] = srs.GetAuthorityCode('PROJCS')
            info['linear_unit_name'] = srs.GetLinearUnitsName()
        except Exception as e:
            logger.debug(f"Error extracting projected info: {e}")
    
    # Compound CS
    if srs.IsCompound():
        try:
            info['compound_cs_name'] = srs.GetAttrValue('COMPD_CS')
        except Exception as e:
            logger.debug(f"Error extracting compound info: {e}")
    
    # Vertical CS
    try:
        wkt = srs.ExportToWkt()
        if 'VERT_CS' in wkt:
            vert_srs = osr.SpatialReference()
            vert_srs.ImportFromWkt(wkt)
            
            vert_name = vert_srs.GetAttrValue('VERT_CS')
            if vert_name:
                info['vertical_cs_name'] = vert_name
                info['vertical_cs_code'] = vert_srs.GetAuthorityCode('VERT_CS')
            
            vert_datum = vert_srs.GetAttrValue('VERT_DATUM')
            if vert_datum:
                info['vertical_datum_name'] = vert_datum
                info['vertical_datum_code'] = vert_srs.GetAuthorityCode('VERT_DATUM')
            
            vert_unit = vert_srs.GetLinearUnitsName()
            if vert_unit:
                info['vertical_unit_name'] = vert_unit
    except Exception as e:
        logger.debug(f"Error extracting vertical info: {e}")
    
    return info

def _calculate_native_bbox(ds: gdal.Dataset, gt: Tuple[float, ...],
                           projection_info: Dict[str, Any]) -> Dict[str, float]:
    """
    Calculate bounding box in native coordinate system.
    
    This replaces geokey_parser.get_geospatial_extents() by calculating
    the bbox once and caching it.
    
    Args:
        ds: GDAL dataset
        gt: GeoTransform tuple
        projection_info: Projection info dict with raster_type
        
    Returns:
        Dictionary with west, east, south, north extents
    """
    if not gt:
        return {}
    
    width = ds.RasterXSize
    height = ds.RasterYSize
    
    # Check if PixelIsPoint (adjust by half pixel)
    is_point = projection_info.get('raster_type') == 'PixelIsPoint'
    half_pixel_x = gt[1] / 2 if is_point else 0
    half_pixel_y = gt[5] / 2 if is_point else 0
    
    return {
        'west': gt[0] + half_pixel_x,
        'east': gt[0] + width * gt[1] - half_pixel_x,
        'south': gt[3] + height * gt[5] - half_pixel_y,
        'north': gt[3] + half_pixel_y
    }

def _calculate_geographic_corners(ds: gdal.Dataset, srs: osr.SpatialReference,
                                   gt: Tuple[float, ...],
                                   projection_info: Dict[str, Any]) -> Optional[Dict[str, Tuple[float, float]]]:
    """
    Calculate geographic (WGS84) corner coordinates.
    
    This replaces geokey_parser.get_geographic_extents() by calculating
    corners once and caching them.
    
    Args:
        ds: GDAL dataset
        srs: Spatial reference system
        gt: GeoTransform tuple
        projection_info: Projection info dict with raster_type
        
    Returns:
        Dictionary with corner names mapping to (lon, lat) tuples, or None
    """
    if not srs or not gt:
        return None
    
    try:
        wkt = srs.ExportToWkt()
        if not wkt:
            return None
        
        width = ds.RasterXSize
        height = ds.RasterYSize
        ulx, xres, xskew, uly, yskew, yres = gt
        
        # Check if PixelIsPoint
        is_point = projection_info.get('raster_type') == 'PixelIsPoint'
        
        def get_coord(pixel, line):
            """Calculate geospatial coordinates from pixel/line coordinates."""
            x = ulx + pixel * xres + line * xskew
            y = uly + pixel * yskew + line * yres
            return (x, y)
        
        if is_point:
            # For PixelIsPoint, coordinates are at pixel centers
            p_ul, l_ul = 0.5, 0.5
            p_lr, l_lr = width - 0.5, height - 0.5
        else:
            # For PixelIsArea, extents are at outer edges
            p_ul, l_ul = 0.0, 0.0
            p_lr, l_lr = float(width), float(height)
        
        # Calculate corner coordinates in native SRS
        native_corners = {
            'Upper Left': get_coord(p_ul, l_ul),
            'Lower Left': get_coord(p_ul, l_lr),
            'Upper Right': get_coord(p_lr, l_ul),
            'Lower Right': get_coord(p_lr, l_lr),
            'Center': get_coord(width / 2.0, height / 2.0)
        }
        
        # If SRS is geographic, return native coordinates directly
        if srs.IsGeographic():
            return native_corners
        
        # If SRS is projected, transform to WGS84
        if srs.IsProjected():
            target_srs = osr.SpatialReference()
            target_srs.ImportFromEPSG(4326)  # WGS84
            
            # Ensure consistent axis ordering for GDAL 3+
            if int(gdal.VersionInfo('VERSION_NUM')[0]) >= 3:
                srs.SetAxisMappingStrategy(osr.OAMS_TRADITIONAL_GIS_ORDER)
                target_srs.SetAxisMappingStrategy(osr.OAMS_TRADITIONAL_GIS_ORDER)
            
            transform = osr.CoordinateTransformation(srs, target_srs)
            
            geo_corners = {}
            for name, (x, y) in native_corners.items():
                lon, lat, _ = transform.TransformPoint(x, y)
                geo_corners[name] = (lon, lat)
            return geo_corners
        
        return None
    except Exception as e:
        logger.debug(f"Error calculating geographic corners: {e}")
        return None

def _get_decimal_precision_for_value(val: float, sigfigs: int) -> int:
    """Helper to find the decimal precision for a single float value."""
    if not np.isfinite(val):
        return 0
    
    # Use Python's Decimal type for exact arithmetic to avoid floating point representation issues.
    # Precision is set high enough to handle double-precision floats.
    getcontext().prec = 30
    
    try:
        d_val = Decimal(str(val))
        
        # Normalize the value by quantization to the maximum significant figures for the data type.
        # This mitigates floating-point noise (e.g., 1.200000047 representing 1.2).
        limit = Decimal(f'1e-{sigfigs}')
        clean_val = d_val.quantize(limit)

        # Iterate to find the minimum decimal precision required to represent the value without data loss.
        for n in range(sigfigs + 1):
            # If rounding to 'n' decimal places results in the same value as the original (clean) value,
            # then 'n' is the effective precision.
            rounded = clean_val.quantize(Decimal(f'1e-{n}'))
            if rounded == clean_val:
                return n
                
        return sigfigs
    except (ValueError, DecimalException):
        # Fallback for values that cause Decimal errors (e.g. extremely large values)
        return 0

def calculate_precision_from_values(vals: np.ndarray, sigfigs: int, nodata: Optional[float] = None) -> int:
    """
    Calculates max decimal precision from a numpy array of values.
    """
    if vals is None or len(vals) == 0:
        return 0

    if nodata is not None:
        # Handle NaN nodata specially
        if isinstance(nodata, float) and np.isnan(nodata):
            vals = vals[~np.isnan(vals)]
        else:
            vals = vals[vals != nodata]
            
    # Also filter NaNs that might be in the data even if nodata wasn't explicitly NaN
    vals = vals[~np.isnan(vals)]

    if len(vals) == 0:
        return 0

    max_precision_found = 0
    for val in vals:
        precision = _get_decimal_precision_for_value(val, sigfigs)
        if precision > max_precision_found:
            max_precision_found = precision
                
            # Optimization: if max possible precision is found, stop early
            if max_precision_found == sigfigs:
                return sigfigs
    return max_precision_found

def calculate_band_precision(band: gdal.Band, sample_size: int = 10000) -> int:
    """
    Detects the decimal rounding precision of a single Float32 or Float64 raster band.

    Helper function used by determine_decimal_precision.

    Args:
        band: GDAL Band object.
        sample_size: Approximate number of pixels to sample.

    Returns:
        The maximum number of decimal places detected in the data.
    """
    if band is None:
        return 0

    # Robustly check data type
    dtype = None
    if hasattr(band, "DataType"):
        dtype = gdal.GetDataTypeName(band.DataType)
    
    if not dtype or 'Float' not in dtype:
        return 0
        
    sigfigs = 7 if dtype == "Float32" else 15
    nodata = band.GetNoDataValue()
    
    # Get dimensions safely
    xsize = getattr(band, "XSize", 0)
    ysize = getattr(band, "YSize", 0)
    
    if xsize <= 0 or ysize <= 0:
        return 0
        
    # Calculate sampling stride
    min_rows = 10
    target_rows = max(min_rows, int(np.ceil(sample_size / xsize)))
    
    step = 1 if target_rows >= ysize else int(ysize / target_rows)
    step = max(1, step)
    
    current_max_precision = 0

    # Iterate through selected rows
    for y in range(0, ysize, step):
        row = band.ReadAsArray(0, y, xsize, 1)
        if row is None:
            continue
            
        precision = calculate_precision_from_values(row.flatten(), sigfigs, nodata)
        if precision > current_max_precision:
            current_max_precision = precision
            if current_max_precision == sigfigs:
                return sigfigs
            
    return current_max_precision

def calculate_precision_from_tifffile_page(page: Any, sample_size: int = 10000) -> Union[int, List[int]]:
    """
    Detects decimal precision from a tifffile Page object.
    
    Useful for overviews/IFDs where GDAL object mapping is ambiguous.
    Supports multi-band pages (returns List[int]).
    """
    if not page:
        return 0
        
    # Check basic properties
    if 'float' not in str(page.dtype):
        # If it's multi-band, we return a list of 0s
        samples_per_pixel = page.samplesperpixel
        if samples_per_pixel > 1:
            return [0] * samples_per_pixel
        return 0
        
    sigfigs = 15 if 'float64' in str(page.dtype) else 7
    nodata = page.nodata
    
    try:
        # Load data into memory. This is safer than slicing for compressed/tiled TIFFs.
        data = page.asarray()
    except Exception:
        # Fallback if asarray fails
        samples_per_pixel = page.samplesperpixel
        if samples_per_pixel > 1:
            return [0] * samples_per_pixel
        return 0

    # Handle shape variations
    # Standard: (H, W) or (H, W, B)
    # Planar Separate: (B, H, W)
    if data.ndim == 2:
        data = data[:, :, np.newaxis] # (H, W, 1)
    elif data.ndim == 3:
        # Check PlanarConfiguration
        # 1 = Contig (H, W, B) - Default
        # 2 = Separate (B, H, W)
        planar_config = getattr(page, 'planarconfig', 1)
        if planar_config == 2:
            data = data.transpose(1, 2, 0) # Convert (B, H, W) -> (H, W, B)
    
    h, w, bands = data.shape
    precisions = [0] * bands
    
    # Calculate striding
    min_rows = 10
    target_rows = max(min_rows, int(np.ceil(sample_size / w)))
    step = max(1, int(h / target_rows) if target_rows < h else 1)
    
    # Iterate through rows in memory
    for y in range(0, h, step):
        row_data = data[y, :, :] # (W, B)
        
        for b in range(bands):
            if precisions[b] == sigfigs:
                continue
            
            vals = row_data[:, b] # (W,)
            p = calculate_precision_from_values(vals, sigfigs, nodata)
            if p > precisions[b]:
                precisions[b] = p
                
    if bands == 1:
        return precisions[0]
    return precisions

def determine_decimal_precision(ds: gdal.Dataset, sample_size: int = 10000) -> Union[int, List[int]]:
    """
    Detects the decimal rounding precision for all bands in a dataset.

    This function determines if a raster's values were rounded to a fixed number
    of decimal places. It samples pixels across the image bands.

    Args:
        ds: Open GDAL dataset.
        sample_size: Approximate number of pixels to sample per band.

    Returns:
        An integer (if single band) or a list of integers (if multi-band) representing
        the maximum number of decimal places detected.
    """
    if ds is None:
        return 0

    precisions = []
    for i in range(ds.RasterCount):
        band = ds.GetRasterBand(i + 1)
        precisions.append(calculate_band_precision(band, sample_size))
        
    if len(precisions) == 1:
        return precisions[0]
    return precisions

def check_transparency(ds: gdal.Dataset) -> Dict[str, Any]:
    """
    Checks for transparency in a raster dataset, including alpha, masks, and NoData.

    Args:
        ds: The GDAL dataset to analyze.

    Returns:
        A dictionary with transparency information.
    """
    transparency_info = {}
    bands = ds.RasterCount
    if bands == 0:
        return transparency_info

    # Check for Alpha Band
    has_alpha_band = any(ds.GetRasterBand(i + 1).GetColorInterpretation() == gdal.GCI_AlphaBand for i in range(bands))
    if has_alpha_band:
        transparency_info['Alpha'] = True

    # Check for Mask
    is_mask_present = False
    try:
        tiff_parser = None
        try:
            tiff_parser = TiffTagParser(ds.GetDescription())
            if len(tiff_parser.tif.pages) > 1:
                ifd1_tags_list = tiff_parser.get_tags(page_index=1)
                ifd1_tags = {tag.code: tag for tag in ifd1_tags_list}
                photometric_tag = ifd1_tags.get(262)
                if photometric_tag and photometric_tag.value == 4:
                    is_mask_present = True
        finally:
            if tiff_parser:
                tiff_parser.close()
        if is_mask_present:
            transparency_info['Mask'] = True
    except (RuntimeError, IndexError) as e:
        logger.warning(f"Could not perform detailed mask check: {e}")

    # Check for NoData
    nodata_str = None
    if bands > 1:
        nodata_values = [ds.GetRasterBand(i + 1).GetNoDataValue() for i in range(bands)]
        if any(v is not None for v in nodata_values):
            nodata_str = ' '.join(map(str, [v for v in nodata_values if v is not None]))
    else:
        nodata_val = ds.GetRasterBand(1).GetNoDataValue()
        if nodata_val is not None:
            # Normalize and detect NaN reliably
            if isinstance(nodata_val, str) and nodata_val.lower() == 'nan':
                nodata_str = 'NaN'
            elif isinstance(nodata_val, (float, np.floating)) and np.isnan(nodata_val):
                nodata_str = 'NaN'
            else:
                band = ds.GetRasterBand(1)
                dtype = gdal.GetDataTypeName(band.DataType)
                if dtype and 'Float' in dtype:
                    nodata_str = f"{float(nodata_val):.16g}"
                else:  # Integer types: convert via float->int to handle values like 0.0
                    nodata_str = str(int(float(nodata_val)))

    if nodata_str:
        transparency_info['NoData'] = nodata_str
        
    return transparency_info

def get_transparency_str(info: GeoTiffInfo) -> str:
    """
    Generate a string summarizing the transparency information of a GeoTIFF.

    Args:
        info: GeoTIFF info object with transparency_info attribute

    Returns:
        A string summarizing transparency components (Alpha, Mask, NoData)
    """
    parts = []
    if info.transparency_info.get('Alpha'):
        parts.append('Alpha')
    if info.transparency_info.get('Mask'):
        parts.append('Mask')
    if info.transparency_info.get('NoData'):
        nodata_val = info.transparency_info['NoData']
        parts.append(f"NoData ({nodata_val})")
    return ', '.join(parts) if parts else 'No'

def get_uncompressed_size(filepath: str) -> float:
    """
    Calculates the theoretical uncompressed size of a dataset by summing all IFDs.

    This function computes the size of the raster as if it were stored
    uncompressed, including the main image, all overviews, and any masks.

    Args:
        filepath: Path to the TIFF file.

    Returns:
        The total uncompressed size in bytes.
    """
    total_uncompressed_size = 0.0
    try:
        tiff = TiffTagParser(filepath)
        for page_index in range(len(tiff.tif.pages)):
            tags_list = tiff.get_tags(page_index=page_index)
            if not tags_list:
                continue
            tags = {tag.code: tag for tag in tags_list}

            width_tag = tags.get(256)
            width = width_tag.value if width_tag else None
            height_tag = tags.get(257)
            height = height_tag.value if height_tag else None
            bit_count_tag = tags.get(258)
            bit_count = bit_count_tag.value if bit_count_tag else 0
            band_count_tag = tags.get(277)
            band_count = band_count_tag.value if band_count_tag else 1

            if not width or not height:
                continue

            if isinstance(bit_count, (list, tuple)):
                total_bits_per_pixel = sum(bit_count)
            else:
                total_bits_per_pixel = bit_count * band_count

            ifd_uncompressed_size = width * height * total_bits_per_pixel / 8
            total_uncompressed_size += ifd_uncompressed_size
        tiff.close()
    except Exception as e:
        logger.warning(f"Could not calculate uncompressed size for {filepath}: {e}")
        return 0.0
    return total_uncompressed_size

def get_lerc_max_z_error(ds: gdal.Dataset) -> str:
    """Extracts LERC Max Z Error from TIFF tags."""
    try:
        if ds.GetMetadataItem('COMPRESSION', 'IMAGE_STRUCTURE') == 'LERC':
            tiff_parser = None
            try:
                tiff_parser = TiffTagParser(ds.GetDescription())
                tags_list = tiff_parser.get_tags()
                tags = {tag.code: tag for tag in tags_list}
                lerc_params_tag = tags.get(LERC_PARAMS_TAG_CODE)
                if lerc_params_tag:
                    lerc_params_str = lerc_params_tag.value
                    if isinstance(lerc_params_str, str):
                        match = re.search(r"MAX_Z_ERROR=(\d+\.?\d*)", lerc_params_str)
                        if match:
                            return f"{float(match.group(1)):.16g}"
                        else:
                            return "0"  # If LERC is used but no MAX_Z_ERROR found, value is 0 (lossless)
            finally:
                if tiff_parser:
                    tiff_parser.close()
    except Exception as e:
        logger.warning(f"Could not read LERC Max Z Error from TIFF tags: {e}")
    return ''

def estimate_image_quality(ds: gdal.Dataset, compression: str) -> str:
    """
    Estimate image quality from metadata if possible.
    
    Args:
        ds: GDAL Dataset
        compression: Compression algorithm name (e.g. 'JXL', 'JPEG')
        
    Returns:
        String representation of quality (e.g. "90", "90 (Est.)", or "N/A")
    """
    if compression == 'JXL':
        # Try to retrieve JXL_DISTANCE from metadata
        # GDAL might store this in default or IMAGE_STRUCTURE domain
        jxl_dist_str = ds.GetMetadataItem("JXL_DISTANCE", "IMAGE_STRUCTURE")
        if not jxl_dist_str:
                jxl_dist_str = ds.GetMetadataItem("JXL_DISTANCE")
        
        if jxl_dist_str:
            try:
                dist = float(jxl_dist_str)
                # Reverse "The Rule of Ten": distance = (100.0 - quality) * 0.1
                # So: quality = 100 - (distance / 0.1)
                quality = 100.0 - (dist / 0.1)
                return f"{int(round(quality))} (Est.)"
            except ValueError:
                pass
        
        # Check for Lossless
        jxl_lossless = ds.GetMetadataItem("JXL_LOSSLESS", "IMAGE_STRUCTURE")
        if jxl_lossless and jxl_lossless.upper() == 'YES':
            return "100 (Lossless)"

    # For JPEG or other formats where quality is not preserved in metadata
    return "N/A"

def calculate_compression_efficiency(filepath: str, tiff: Optional[tifffile.TiffFile] = None, debug: bool = False) -> float:
    """
    Calculate comprehensive compression efficiency across ALL IFDs (main image, overviews, masks, etc.).
    
    This function provides OVERALL file compression efficiency by summing compressed/uncompressed
    sizes across all IFDs. Use this when you need a single efficiency metric for the entire file.
    
    For PER-IFD compression analysis (useful for detailed reports), use the per-IFD calculation
    logic in report_helpers.get_ifd_table_for_markdown() instead.
    
    This function properly accounts for:
    - Main image data (IFD 0)
    - Overview pyramids (reduced resolution IFDs)
    - Transparency masks (1-bit masks)
    - Thumbnails and other associated images
    - Different compression settings per IFD (if applicable)
    
    Args:
        filepath: Path to the TIFF file
        tiff: An optional, already opened TiffFile object to avoid reopening the file.
        debug: Enable debug logging for detailed IFD analysis
        
    Returns:
        Compression efficiency as a percentage string (e.g., "45.2") or "0.0" for uncompressed/failures
    """
    try:
        from pathlib import Path
        
        tiff_parser = TiffTagParser(str(filepath), tiff_file=tiff)
        total_compressed_size = 0
        total_uncompressed_size = 0
        has_compressed_data = False
        
        if debug:
            logger.debug(f"Analyzing {len(tiff_parser.tif.pages)} IFDs in {Path(filepath).name}")
        
        # Iterate through ALL IFDs (main image + overviews + masks + other associated images)
        for page_index in range(len(tiff_parser.tif.pages)):
            try:
                tags_list = tiff_parser.get_tags(page_index=page_index)
                if not tags_list:
                    continue
                tags = {tag.code: tag for tag in tags_list}
                    
                # Get basic image properties for this IFD
                width_tag = tags.get(256)
                width = width_tag.value if width_tag else None
                height_tag = tags.get(257)
                height = height_tag.value if height_tag else None
                bit_count_tag = tags.get(258)
                bit_count = bit_count_tag.value if bit_count_tag else 0
                band_count_tag = tags.get(277)
                band_count = band_count_tag.value if band_count_tag else 1
                compression_tag = tags.get(259)
                compression_code = compression_tag.value if compression_tag else 1
                algo_interp = compression_tag.interpretation if compression_tag else ''
                
                if not width or not height:
                    if debug:
                        logger.debug(f"  IFD {page_index}: Missing dimensions, skipping")
                    continue
                    
                # Handle bit_count as tuple/list (multiple bands) or single value
                if isinstance(bit_count, (list, tuple)):
                    total_bits_per_pixel = sum(bit_count) * band_count if band_count > len(bit_count) else sum(bit_count)
                else:
                    total_bits_per_pixel = bit_count * band_count if bit_count else 8 * band_count
                
                # Determine if tiled or striped for this IFD
                tile_width_tag = tags.get(322)
                tile_width = tile_width_tag.value if tile_width_tag else None
                is_tiled = tile_width is not None
                
                # Get actual compressed byte counts. Prefer raw tifffile page tag values over parsed values to
                # avoid the summarized/display strings produced by TiffTagParser for large binary arrays.
                byte_counts_tag_code = 325 if is_tiled else 279  # TileByteCounts or StripByteCounts
                byte_counts = None
                try:
                    page_obj = tiff_parser.tif.pages[page_index]
                    page_tags = getattr(page_obj, 'tags', None)
                    raw_tag = page_tags.get(byte_counts_tag_code) if page_tags is not None else None
                    if raw_tag is not None:
                        byte_counts = raw_tag.value
                except Exception:
                    byte_counts = None

                # Fall back to the parsed/display tag if raw access failed
                if byte_counts is None:
                    byte_counts_tag = tags.get(byte_counts_tag_code)
                    byte_counts = byte_counts_tag.value if byte_counts_tag else None
                
                if byte_counts:
                    # Calculate sizes for this IFD
                    if isinstance(byte_counts, (list, tuple, np.ndarray)):
                        byte_counts = sum(int(b) for b in byte_counts)
                    else:
                        byte_counts = int(byte_counts)

                    ifd_compressed_size = byte_counts
                    ifd_uncompressed_size = width * height * total_bits_per_pixel / 8
                    
                    total_compressed_size += ifd_compressed_size
                    total_uncompressed_size += ifd_uncompressed_size
                    
                    # Track if we found any actually compressed data
                    if compression_code != 1 and not (algo_interp and "uncompressed" in algo_interp.lower()):
                        has_compressed_data = True
                    
                    if debug:
                        subfile_type_tag = tags.get(254)
                        subfile_type = subfile_type_tag.interpretation if subfile_type_tag else 'Unknown'
                        logger.debug(f"  IFD {page_index} ({subfile_type}): {width}x{height}, {total_bits_per_pixel}bpp, "
                                   f"{ifd_compressed_size:,} compressed / {ifd_uncompressed_size:,} uncompressed bytes")
                else:
                    if debug:
                        logger.debug(f"  IFD {page_index}: No byte count data available")
                    
            except Exception as e:
                if debug:
                    logger.debug(f"  Error processing IFD {page_index}: {e}")
                continue
        
        tiff_parser.close()
        
        # Calculate overall compression efficiency
        if total_uncompressed_size > 0 and has_compressed_data:
            efficiency = (1 - (total_compressed_size / total_uncompressed_size)) * 100
            if debug:
                logger.debug(f"  Final efficiency calculation: Total compressed={total_compressed_size}, Total uncompressed={total_uncompressed_size}, Has compressed data={has_compressed_data}, Efficiency={efficiency:.1f}%")
            return efficiency
        else:
            if debug:
                logger.debug("  Final efficiency calculation: No compressed data found or calculation failed. Returning 0.0")
            return 0.0  # Uncompressed or calculation failed
        
    except Exception as e:
        if debug:
            logger.debug(f"Could not calculate compression efficiency for {filepath}: {e}")
        return 0.0

def is_nodata_valid(nodata: float, dtype: str) -> bool:
    """
    Check if NoData value is within the valid range for the given data type.
    
    Args:
        nodata: The NoData value to validate
        dtype: The GDAL data type string (e.g., 'Float32', 'Int16', 'Byte')
        
    Returns:
        True if NoData value is valid for the data type, False otherwise
        
    Examples:
        >>> is_nodata_valid(-3.4e38, 'Float32')  # Out of range
        False
        >>> is_nodata_valid(np.nan, 'Float32')  # Valid for floats
        True
        >>> is_nodata_valid(-32768, 'Int16')  # Valid
        True
    """
    if np.isnan(nodata):
        # NaN is always valid for floating-point types
        return 'Float' in dtype
    
    if 'Float32' in dtype:
        finfo = np.finfo(np.float32)
        return bool(abs(nodata) < finfo.max)
    elif 'Float64' in dtype:
        finfo = np.finfo(np.float64)
        return bool(abs(nodata) < finfo.max)
    elif 'Int16' in dtype:
        iinfo = np.iinfo(np.int16)
        return bool(iinfo.min <= nodata <= iinfo.max)
    elif 'Int32' in dtype:
        iinfo = np.iinfo(np.int32)
        return bool(iinfo.min <= nodata <= iinfo.max)
    elif 'UInt16' in dtype:
        iinfo = np.iinfo(np.uint16)
        return bool(iinfo.min <= nodata <= iinfo.max)
    elif 'UInt32' in dtype:
        iinfo = np.iinfo(np.uint32)
        return bool(iinfo.min <= nodata <= iinfo.max)
    elif 'Byte' in dtype:
        iinfo = np.iinfo(np.uint8)
        return bool(iinfo.min <= nodata <= iinfo.max)
    
    # Unknown type, assume valid
    return True

def remap_nodata_value(ds: gdal.Dataset, source_nodata: float, target_nodata: float) -> gdal.Dataset:
    """
    Remaps input NoData values to the user-provided target NoData value, if different.
    """
    total_remapped_pixels = 0

    for i in range(1, ds.RasterCount + 1):
        band = ds.GetRasterBand(i)
        array = band.ReadAsArray()

        # Remap source NoData to target NoData
        if np.isnan(source_nodata):
            nodata_mask = np.isnan(array)
        else:
            nodata_mask = array == source_nodata
        
        num_nodata_pixels = np.sum(nodata_mask)
        if num_nodata_pixels > 0:
            total_remapped_pixels += num_nodata_pixels
            if np.isnan(target_nodata):
                array[nodata_mask] = np.nan
            else:
                array[nodata_mask] = target_nodata
        
        band.WriteArray(array.astype(np.float32)) # Write back as float32
        band.FlushCache()

    if total_remapped_pixels > 0:
        logger.info(
            f"Remapped {total_remapped_pixels} pixels from source NoData ({source_nodata}) "
            f"to target NoData ({target_nodata}) across all bands."
        )
    else:
        logger.info(f"No pixels matching the source NoData value ({source_nodata}) were found. No remapping was performed.")
    
    return ds

def normalize_existing_mask(ds: gdal.Dataset) -> None:
    """
    Normalizes an existing transparency mask to ensure valid pixels are opaque (255).
    
    This fixes issues where 1-bit masks might be read as 0/1 values by GDAL, which
    would be interpreted as nearly transparent (1/255) when written to an 8-bit mask band.
    It also ensures the mask band does not have a NoData value set.
    """
    if ds.RasterCount == 0:
        return

    try:
        band1 = ds.GetRasterBand(1)
        mask_flags = band1.GetMaskFlags()
        
        # Only normalize if we have a per-dataset mask or alpha (not GMF_ALL_VALID or GMF_NODATA)
        if not (mask_flags & gdal.GMF_PER_DATASET) and not (mask_flags & gdal.GMF_ALPHA):
            return

        logger.info("Checking existing transparency mask for normalization...")
        mask_band = band1.GetMaskBand()
        mask_array = mask_band.ReadAsArray()
        
        mask_array = mask_array.astype(np.uint8)
        
        # Normalize: Any non-zero value becomes 255 (Opaque)
        if mask_array.max() > 0:
             mask_array[mask_array > 0] = 255
             mask_band.WriteArray(mask_array)
             mask_band.FlushCache()
        
        # Ensure mask band has no NoData value (which would cause opaque pixels to be treated as NoData)
        try:
            mask_band.DeleteNoDataValue()
        except Exception:
            pass
            
    except Exception as e:
        logger.warning(f"Failed to normalize existing mask: {e}")

def mask_nodata_value(ds: gdal.Dataset, nodata_value: float) -> gdal.Dataset:
    """
    Converts pixels with the NoData value to a transparency mask, then unsets NoData.
    
    This function performs the following steps:
    1. Validates that the NoData value is within the valid range for the data type
    2. Checks if any pixels actually match the NoData value
    3. If both conditions are met, adds matching pixels to the transparency mask (IFD 1)
    4. Unsets the NoData value from all bands
    
    If a mask already exists, pixels are added to it (masks are additive).
    If the NoData value is invalid or no pixels match it, the NoData value is
    simply unset without creating a mask.
    
    Args:
        ds: GDAL dataset with a NoData value to convert to mask
        nodata_value: The NoData value to mask
        
    Returns:
        The modified GDAL dataset with mask instead of NoData value
    """
    if ds.RasterCount == 0:
        logger.warning("Dataset has no bands. Cannot process NoData mask.")
        return ds
    
    # Step 1: Validate NoData value is within valid range for data type
    band = ds.GetRasterBand(1)
    data_type = gdal.GetDataTypeName(band.DataType)
    
    if not is_nodata_valid(nodata_value, data_type):
        logger.info(
            f"NoData value {nodata_value} is out of range for {data_type}. "
            f"Unsetting NoData without creating mask."
        )
        for i in range(1, ds.RasterCount + 1):
            ds.GetRasterBand(i).DeleteNoDataValue()
        ds.FlushCache()
        return ds
    
    # Step 2: Check if any pixels actually have this NoData value
    logger.info(f"Scanning for pixels matching NoData value {nodata_value}...")
    has_nodata_pixels = False
    nodata_mask_combined = None
    
    for i in range(1, ds.RasterCount + 1):
        band = ds.GetRasterBand(i)
        array = band.ReadAsArray()
        
        # Create mask for NoData pixels
        if np.isnan(nodata_value):
            band_nodata_mask = np.isnan(array)
        else:
            band_nodata_mask = (array == nodata_value)
        
        if np.any(band_nodata_mask):
            has_nodata_pixels = True
            # Combine masks across bands (logical AND)
            # A pixel should only be masked if it is NoData in ALL bands.
            if nodata_mask_combined is None:
                nodata_mask_combined = band_nodata_mask
            else:
                nodata_mask_combined = nodata_mask_combined & band_nodata_mask
    
    if not has_nodata_pixels or nodata_mask_combined is None:
        logger.info(
            f"No pixels matching NoData value {nodata_value}. "
            f"Unsetting NoData without creating mask."
        )
        for i in range(1, ds.RasterCount + 1):
            ds.GetRasterBand(i).DeleteNoDataValue()
        ds.FlushCache()
        return ds
    
    # Step 3: Create or update transparency mask
    # At this point, nodata_mask_combined is guaranteed to be not None
    band1 = ds.GetRasterBand(1)
    
    # Try to get existing mask
    mask_band = band1.GetMaskBand()
    mask_flags = band1.GetMaskFlags()
    logger.info(f"Initial Mask Flags: {mask_flags}")
    
    # Check if mask already exists
    if mask_flags == gdal.GMF_ALL_VALID:
        # No existing mask (GMF_ALL_VALID), create one
        logger.info("Creating transparency mask for NoData pixels.")
        band1.CreateMaskBand(gdal.GMF_PER_DATASET)
        mask_band = band1.GetMaskBand()
        # Initialize with all opaque (255 = valid/opaque)
        mask_array = np.full((ds.RasterYSize, ds.RasterXSize), 255, dtype=np.uint8)
    elif (mask_flags & gdal.GMF_NODATA):
        # Implicit mask derived from NoData value (GMF_NODATA).
        # DO NOT read it. Start fresh to ensure we use our correct multi-band AND logic.
        logger.info("Materializing implicit NoData mask to explicit transparency mask (resetting to opaque).")
        
        # Create a real PER_DATASET mask band
        band1.CreateMaskBand(gdal.GMF_PER_DATASET)
        mask_band = band1.GetMaskBand()
        
        # Initialize with all opaque (255 = valid/opaque)
        mask_array = np.full((ds.RasterYSize, ds.RasterXSize), 255, dtype=np.uint8)
        mask_band.WriteArray(mask_array)
    else:
        # Existing explicit mask (likely GMF_PER_DATASET or GMF_ALPHA), read it
        logger.info("Adding NoData pixels to existing explicit transparency mask.")
        mask_array = mask_band.ReadAsArray()
        
        # Normalize mask values to 0 (transparent) and 255 (opaque).
        # Some 1-bit masks might be read as 0/1, which when written back to an 8-bit mask
        # would result in 1/255 opacity (invisible). We ensure all valid pixels are 255.
        mask_array[mask_array > 0] = 255
    
    # Add NoData pixels to mask (set to 0 = transparent/masked)
    # Mask is additive: once masked, stays masked
    mask_array[nodata_mask_combined] = 0
    
    # Write mask back
    mask_band.WriteArray(mask_array)
    
    # CRITICAL: Ensure the mask band itself does NOT have a NoData value.
    try:
        mask_band.DeleteNoDataValue()
    except Exception:
        pass # Ignore errors
        
    mask_band.FlushCache()
    
    total_masked_pixels = int(np.sum(nodata_mask_combined))
    logger.info(f"Added {total_masked_pixels:,} NoData pixels to transparency mask.")
    
    # Step 4: Unset NoData value from all bands
    for i in range(1, ds.RasterCount + 1):
        ds.GetRasterBand(i).DeleteNoDataValue()
    
    logger.info("NoData value unset. Transparency is now handled via mask.")
    ds.FlushCache()
    return ds

def read_geotiff(ds: gdal.Dataset) -> GeoTiffInfo:
    """
    Extracts ALL key information from a GDAL dataset into a GeoTiffInfo dataclass.
    
    This is the central extraction point - GDAL is opened ONCE here and all
    metadata is extracted and cached. This eliminates redundant GDAL opens
    and redundant calculations across the codebase.

    Args:
        ds: The GDAL dataset to analyze.

    Returns:
        A GeoTiffInfo object populated with the dataset's metadata, including
        cached projection info, bounding box, and geographic corners.
    """
    filepath = ds.GetDescription()
    gt = ds.GetGeoTransform()
    wkt = ds.GetProjection()
    srs = osr.SpatialReference(wkt=wkt)
    vert_srs = get_vertical_srs(ds)
    vert_srs_name = vert_srs.GetName() if vert_srs else None
    projection_info = _retrieve_projection_info(ds, srs)
    native_bbox = _calculate_native_bbox(ds, gt, projection_info) if gt else None
    geographic_corners = _calculate_geographic_corners(ds, srs, gt, projection_info) if gt and srs else None
    bands = ds.RasterCount
    data_type, nodata_val, color_interp_name, has_alpha_band = None, None, None, False
    
    if bands > 0:
        band1 = ds.GetRasterBand(1)
        data_type = gdal.GetDataTypeName(band1.DataType)
        nodata_val = band1.GetNoDataValue()
        color_interp_name = gdal.GetColorInterpretationName(band1.GetColorInterpretation())
        has_alpha_band = any(ds.GetRasterBand(i + 1).GetColorInterpretation() == gdal.GCI_AlphaBand for i in range(bands))

    transparency_info = check_transparency(ds)

    return GeoTiffInfo(
        filepath=filepath, x_size=ds.RasterXSize, y_size=ds.RasterYSize, bands=bands,
        wkt_string=wkt, geo_transform=gt, res_x=abs(gt[1]), res_y=abs(gt[5]), srs=srs,
        vertical_srs=vert_srs, vertical_srs_name=vert_srs_name, data_type=data_type,
        nodata=nodata_val, color_interp=color_interp_name, has_alpha=has_alpha_band,
        transparency_info=transparency_info, projection_info=projection_info,
        native_bbox=native_bbox, geographic_corners=geographic_corners
    )
