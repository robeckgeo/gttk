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
Core GeoTIFF Processing and Analysis Utilities.

This module provides a suite of low-level functions for interacting with GeoTIFF
files using GDAL. It serves as the primary interface for extracting metadata,
calculating metrics like compression efficiency, handling NoData values, and
managing transparency masks.
"""
import re
import logging
import numpy as np
from pathlib import Path
import tifffile
from decimal import Decimal, DecimalException, getcontext
from osgeo import gdal, osr
from typing import Any, Optional, Dict, List, Tuple, Union
from gttk.utils.data_models import GeoTiffInfo
from gttk.utils.gdal_runner import get_projection_info_from_osgeo4w
from gttk.utils.srs_logic import get_vertical_srs
from gttk.utils.tiff_tag_parser import TiffTagParser

LERC_PARAMS_TAG_CODE = 50674

logger = logging.getLogger(__name__)

def _parse_json_projection_info(json_info: Dict[str, Any]) -> Dict[str, Any]:
    """
    Parse projection info from GDAL JSON output (bypassing osr library).
    
    This is used when the main process's GDAL cannot resolve SRS definitions
    (e.g., inside ArcGIS Pro without PROJ_LIB set correctly). It extracts
    details directly from the JSON returned by the OSGeo4W subprocess.
    
    The gdalinfo -json output includes PROJJSON in stac.proj:projjson field.
    """
    info = {}
    
    if not json_info:
        return info
        
    # Get metadata for raster type
    metadata = json_info.get('metadata', {}).get('', {})
    raster_type = metadata.get('AREA_OR_POINT', 'Area').lower()
    info['raster_type'] = 'PixelIsArea' if raster_type == 'area' else 'PixelIsPoint'
    
    # PROJJSON is available in the stac.proj:projjson field!
    stac = json_info.get('stac', {})
    projjson = stac.get('proj:projjson')
    
    if not projjson:
        logger.warning("No PROJJSON found in stac section, falling back to WKT parsing")
        # Fallback: try to extract basic info from WKT
        cs = json_info.get('coordinateSystem', {})
        wkt = cs.get('wkt', '')
        if wkt:
            info['is_geographic'] = 'GEOGCRS' in wkt or 'GEOGCS' in wkt
            info['is_projected'] = 'PROJCRS' in wkt or 'PROJCS' in wkt
            info['is_compound'] = 'COMPOUNDCRS' in wkt or 'COMPD_CS' in wkt
        return info
    
    logger.info("Found PROJJSON in gdalinfo output, parsing...")
    
    # Common helper to get authority code (EPSG) safely
    def get_auth_code(node):
        if 'id' in node:
            id_obj = node['id']
            if isinstance(id_obj, dict):
                return str(id_obj.get('code'))
        return None
    
    # Determine CRS type from PROJJSON
    crs_type = projjson.get('type', '')
    info['is_geographic'] = crs_type == 'GeographicCRS'
    info['is_projected'] = crs_type == 'ProjectedCRS'
    info['is_compound'] = crs_type == 'CompoundCRS'
    
    # --- Geographic CRS (or base CRS of projected) ---
    geo_crs_node = None
    if info['is_projected']:
        geo_crs_node = projjson.get('base_crs')
    elif info['is_geographic']:
        geo_crs_node = projjson
    
    if geo_crs_node:
        info['geographic_cs_name'] = geo_crs_node.get('name')
        info['geographic_cs_code'] = get_auth_code(geo_crs_node)
        
        # Handle both 'datum' and 'datum_ensemble' structures
        datum_node = geo_crs_node.get('datum') or geo_crs_node.get('datum_ensemble')
        if datum_node:
            info['datum_name'] = datum_node.get('name')
            info['datum_code'] = get_auth_code(datum_node)
            
            ellipsoid_node = datum_node.get('ellipsoid')
            if ellipsoid_node:
                info['ellipsoid_name'] = ellipsoid_node.get('name')
                info['semi_major'] = ellipsoid_node.get('semi_major_axis')
                info['inv_flattening'] = ellipsoid_node.get('inverse_flattening')
        
        # Check coordinate_system axes
        cs_node = geo_crs_node.get('coordinate_system', {})
        axes = cs_node.get('axis', [])
        if axes:
            # Get angular unit from first axis (longitude/latitude)
            unit = axes[0].get('unit')
            if unit:
                info['angular_unit_name'] = unit
            
            # Check for 3D geographic CRS (has ellipsoidal height as 3rd axis)
            # Example: EPSG:4979 (WGS 84 3D) has lon, lat, ellipsoidal height
            if len(axes) >= 3:
                third_axis = axes[2]
                # Check if it's ellipsoidal height (vertical component)
                axis_name = third_axis.get('name', '').lower()
                if 'height' in axis_name or 'ellipsoidal' in axis_name:
                    vert_unit = third_axis.get('unit')
                    if vert_unit:
                        info['vertical_unit_name'] = vert_unit
                        logger.info(f"3D Geographic CRS detected with vertical unit: {vert_unit}")
    
    # --- Projected CRS Info ---
    if info['is_projected']:
        info['projected_cs_name'] = projjson.get('name')
        info['projected_cs_code'] = get_auth_code(projjson)
        
        # Linear unit from coordinate_system axes
        cs_node = projjson.get('coordinate_system', {})
        axes = cs_node.get('axis', [])
        if axes:
            # Get unit from first axis (easting/northing)
            unit = axes[0].get('unit')
            if unit:
                info['linear_unit_name'] = unit
    
    # --- Compound CRS Info ---
    if info['is_compound']:
        info['compound_cs_name'] = projjson.get('name')
        
        # Look for components
        components = projjson.get('components', [])
        for comp in components:
            if comp.get('type') == 'VerticalCRS':
                info['vertical_cs_name'] = comp.get('name')
                info['vertical_cs_code'] = get_auth_code(comp)
                
                datum_node = comp.get('datum')
                if datum_node:
                    info['vertical_datum_name'] = datum_node.get('name')
                    info['vertical_datum_code'] = get_auth_code(datum_node)
                
                # Vertical unit
                cs_node = comp.get('coordinate_system', {})
                axes = cs_node.get('axis', [])
                if axes:
                    unit = axes[0].get('unit')
                    if unit:
                        info['vertical_unit_name'] = unit
                break
    
    logger.info(f"Parsed PROJJSON: {info}")
    return info

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
    
    # CS types - convert to bool (GDAL returns 1/0)
    info['is_geographic'] = bool(srs.IsGeographic())
    info['is_projected'] = bool(srs.IsProjected())
    info['is_compound'] = bool(srs.IsCompound())
    
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
    
    # Vertical CS (compound CRS)
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
    
    # Check for 3D Geographic CRS (e.g., EPSG:4979)
    # These have ellipsoidal height as 3rd axis but no separate VERT_CS
    if info['is_geographic'] and not info.get('vertical_unit_name'):
        try:
            if hasattr(srs, 'GetAxesCount'):
                axis_count = srs.GetAxesCount()
                if axis_count == 3:
                    # Check if 3rd axis is vertical/height
                    axis_name = srs.GetAxisName(None, 2)
                    if axis_name and ('height' in axis_name.lower() or 'ellipsoid' in axis_name.lower()):
                        # Get linear unit for the 3rd axis
                        linear_unit = srs.GetLinearUnitsName()
                        if linear_unit:
                            info['vertical_unit_name'] = linear_unit
                            logger.info(f"3D Geographic CRS detected with vertical unit: {linear_unit}")
        except Exception as e:
            logger.debug(f"Error checking for 3D geographic CRS: {e}")
    
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
        
        # If SRS is projected, transform to WGS 84
        if srs.IsProjected():
            target_srs = osr.SpatialReference()
            target_srs.ImportFromEPSG(4326)  # WGS 84
            
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
    
    if len(precisions) == 0:
        return 0
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

def get_uncompressed_size(filepath: str) -> Optional[float]:
    """
    Calculates the theoretical uncompressed size of a dataset by summing all IFDs.

    This function computes the size of the raster as if it were stored
    uncompressed, including the main image, all overviews, and any masks.

    Args:
        filepath: Path to the TIFF file.

    Returns:
        The total uncompressed size in bytes, or None when it could not be determined
        (the reason is logged at warning). It used to return 0.0 for that case, which is
        not a size any raster has.
    """
    total_uncompressed_size = 0.0
    try:
        with TiffTagParser(filepath) as tiff:
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
    except Exception as e:
        logger.warning(f"Uncompressed size unknown for {Path(filepath).name}: {e}")
        return None
    if total_uncompressed_size == 0:
        logger.warning(f"Uncompressed size unknown for {Path(filepath).name}: no IFD carried dimensions")
        return None
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

def _is_transparency_mask_ifd(tags: Dict[int, Any]) -> bool:
    """
    Detect if an IFD represents a transparency mask.
    
    Transparency masks are 1-bit images with photometric interpretation = 4 (TransparencyMask).
    These are ALWAYS compressed with DEFLATE by GDAL, even when COMPRESSION=NONE is specified.
    
    Args:
        tags: Dictionary of TIFF tags (code -> tag object)
        
    Returns:
        True if this IFD is a transparency mask, False otherwise
    """
    try:
        # Get photometric interpretation (tag 262)
        photometric_tag = tags.get(262)
        if not photometric_tag:
            return False
        
        photometric = photometric_tag.value if hasattr(photometric_tag, 'value') else photometric_tag
        
        # Get bits per sample (tag 258)
        bits_per_sample_tag = tags.get(258)
        if not bits_per_sample_tag:
            return False
        
        bits_per_sample = bits_per_sample_tag.value if hasattr(bits_per_sample_tag, 'value') else bits_per_sample_tag
        
        # Handle bits_per_sample as list or single value
        if isinstance(bits_per_sample, (list, tuple)):
            bits_per_sample = bits_per_sample[0] if bits_per_sample else 0
        
        # Mask criteria: photometric=4 (TransparencyMask) AND 1-bit data
        is_mask = (photometric == 4 and bits_per_sample == 1)
        
        return is_mask
    except Exception:
        return False


def _estimate_ifd_header_size(page_index: int, tiff_file: tifffile.TiffFile, tags: Dict[int, Any]) -> Optional[int]:
    """
    Estimate the size of IFD header and metadata overhead.
    
    This includes:
    - IFD directory entries (tag count + tag entries)
    - Tag value data stored outside the IFD structure
    - Strip/Tile offset arrays
    - GeoKey directory structures
    
    Args:
        page_index: Index of the IFD page
        tiff_file: Opened tifffile.TiffFile object
        tags: Dictionary of TIFF tags for this IFD
        
    Returns:
        Estimated header size in bytes, or None when the IFD's tags could not be read
        (logged at warning). It used to answer 1024 -- "a typical IFD with ~50 tags" --
        for any failure, and 0 for a tag whose value could not be read.
    """
    try:
        page = tiff_file.pages[page_index]
        is_bigtiff = tiff_file.is_bigtiff
        
        # Get page tags safely
        page_tags = getattr(page, 'tags', None)
        if page_tags is None:
            # Fallback: use the tags dict passed in
            num_tags = len(tags)
            # Basic IFD directory estimate
            if is_bigtiff:
                return 8 + (20 * num_tags) + 8
            else:
                return 2 + (12 * num_tags) + 4
        
        # IFD directory structure:
        # - Entry count: 2 bytes (classic) or 8 bytes (BigTIFF)
        # - Each tag entry: 12 bytes (classic) or 20 bytes (BigTIFF)
        # - Next IFD offset: 4 bytes (classic) or 8 bytes (BigTIFF)
        num_tags = len(page_tags)
        
        if is_bigtiff:
            ifd_dir_size = 8 + (20 * num_tags) + 8
        else:
            ifd_dir_size = 2 + (12 * num_tags) + 4
        
        # Tag value data: Values that don't fit in the tag entry are stored separately
        # This includes arrays (offsets, byte counts), strings, etc.
        tag_value_data_size = 0
        
        for tag_code, tag_obj in page_tags.items():
            # Offset/byte count arrays (stored outside IFD)
            if tag_code in [273, 279, 324, 325]:  # StripOffsets, StripByteCounts, TileOffsets, TileByteCounts
                # These are typically uint32 or uint64 arrays
                value = tag_obj.value
                if isinstance(value, (list, tuple, np.ndarray)):
                    element_size = 8 if is_bigtiff else 4
                    tag_value_data_size += len(value) * element_size
            
            # String values (stored outside IFD if > 4 bytes for classic, > 8 for BigTIFF)
            elif tag_code in [270, 305, 306, 315, 316, 317]:  # Description, Software, DateTime, Artist, etc.
                value = tag_obj.value
                if isinstance(value, str):
                    # Add null terminator
                    str_size = len(value.encode('utf-8')) + 1
                    threshold = 8 if is_bigtiff else 4
                    if str_size > threshold:
                        tag_value_data_size += str_size
            
            # GeoKey directory (tag 34735) - stored as array of uint16
            elif tag_code == 34735:
                value = tag_obj.value
                if isinstance(value, (list, tuple, np.ndarray)):
                    tag_value_data_size += len(value) * 2  # uint16
            
            # Other array tags stored outside IFD
            elif tag_code in [34736, 34737]:  # GeoDoubleParams, GeoAsciiParams
                value = tag_obj.value
                if tag_code == 34736 and isinstance(value, (list, tuple, np.ndarray)):
                    tag_value_data_size += len(value) * 8  # doubles
                elif tag_code == 34737 and isinstance(value, str):
                    tag_value_data_size += len(value.encode('utf-8'))
        
        total_header_size = ifd_dir_size + tag_value_data_size
        
        return total_header_size
    except Exception as e:
        logger.warning(f"IFD {page_index} header size unknown: {e}")
        return None


def _generate_temp_baseline(source_file: str, arc_mode: bool = False, debug: bool = False) -> Optional[str]:
    """
    Generate temporary uncompressed baseline file for compression efficiency comparison.
    
    This is a dev-only helper function for validating refined estimation accuracy.
    It creates an uncompressed copy of the source file to serve as a baseline.
    
    Args:
        source_file: Path to source GeoTIFF file
        arc_mode: Whether to use ArcGIS-compatible mode (subprocess via gdal_runner)
        debug: Enable debug logging
        
    Returns:
        Path to temporary baseline file, or None if generation failed
    """
    import tempfile
    
    try:
        # Import optimization tools and arguments
        from gttk.utils.script_arguments import OptimizeArguments
        
        # Create temp directory and baseline path
        temp_dir = Path(tempfile.mkdtemp(prefix="gttk_baseline_"))
        baseline_path = temp_dir / f"baseline_{Path(source_file).stem}.tif"
        
        if debug:
            logger.debug(f"Generating temporary baseline: {baseline_path}")
        
        # Create arguments for uncompressed conversion
        # Note: We use 'image' as a generic type since we're just copying with COMPRESSION=NONE
        args = OptimizeArguments(
            input_path=Path(source_file),
            output_path=baseline_path,
            product_type='image',  # Generic type for baseline
            algorithm='NONE',
            cog=False,
            overviews=False,
            open_report=False,
            geo_metadata=False,
            write_pam_xml=False,
            arc_mode=arc_mode
        )
        
        # Generate baseline file - import and call based on mode
        if arc_mode:
            import gttk.tools.optimize_compression_arc as optimize_arc
            return_code = optimize_arc.optimize_compression(args)
        else:
            from gttk.tools.optimize_compression import optimize_compression
            return_code = optimize_compression(args)
        
        if return_code != 0 or not baseline_path.exists():
            logger.error(f"Baseline generation failed with return code: {return_code}")
            return None
        
        if debug:
            logger.debug(f"Baseline generated successfully: {baseline_path} ({baseline_path.stat().st_size:,} bytes)")
        
        return str(baseline_path)
        
    except Exception as e:
        logger.error(f"Error generating baseline file: {e}")
        return None


def calculate_compression_efficiency(
    filepath: str,
    tiff: Optional[tifffile.TiffFile] = None,
    debug: bool = False,
    generate_baseline: bool = False,
    baseline_file: Optional[str] = None,
    arc_mode: bool = False
) -> Optional[float]:
    """
    Calculate compression efficiency with accurate overhead accounting.
    
    This function calculates compression efficiency by properly separating:
    1. Compressible data (image pixels affected by compression algorithm choice)
    2. Invariant overhead (components unchanged by compression algorithm)
    
    Invariant overhead includes:
    - TIFF file headers
    - IFD directory structures and tag metadata
    - Transparency masks (always DEFLATE-compressed, even with COMPRESSION=NONE)
    - GeoKeys and other metadata
    
    By excluding overhead from both numerator and denominator, we get accurate
    compression efficiency that matches actual file size comparisons against
    uncompressed baselines.
    
    **Baseline Generation (Dev-Only Feature)**:
    
    By default, this function uses refined estimation (Phase 1) which is fast and
    accurate (±2% error). For maximum accuracy or validation purposes, you can
    enable baseline file generation:
    
    - `generate_baseline=True`: Generate temporary uncompressed baseline file
    - `baseline_file="path"`: Use existing baseline file (avoids temp file creation)
    
    These options are dev-only and not exposed to CLI commands. All production
    tools use refined estimation by default.
    
    For PER-IFD compression analysis (useful for detailed reports), use the per-IFD
    calculation logic in report_helpers.get_ifd_table_for_markdown() instead.
    
    Args:
        filepath: Path to the TIFF file
        tiff: An optional, already opened TiffFile object to avoid reopening the file
        debug: Enable debug logging for detailed IFD analysis
        generate_baseline: [Dev-only] If True, generate temp baseline file for 100% accuracy
        baseline_file: [Dev-only] Path to pre-existing baseline file (optimization)
        arc_mode: [Dev-only] Use ArcGIS-compatible mode for baseline generation
        
    Returns:
        Compression efficiency as a percentage (e.g., 45.2); 0.0 for an uncompressed file;
        None when it could not be determined, with the reason logged at warning. An error
        and "uncompressed" used to be the same 0.0, and a report could not tell them apart.
        
    Examples:
        >>> # Standard usage (refined estimation, fast)
        >>> efficiency = calculate_compression_efficiency('compressed.tif')
        
        >>> # Dev-only: Generate baseline for validation
        >>> efficiency = calculate_compression_efficiency('compressed.tif', generate_baseline=True)
        
        >>> # Dev-only: Use existing baseline (e.g., in compare_compression)
        >>> efficiency = calculate_compression_efficiency('compressed.tif', baseline_file='baseline.tif')
    """
    # --- Baseline Generation Mode (Dev-Only) ---
    if generate_baseline or baseline_file:
        
        if debug:
            logger.debug("Using baseline file approach for 100% accuracy")
        
        baseline_path: Optional[str] = None
        cleanup_baseline: bool = False
        
        # Generate or use provided baseline
        if baseline_file and Path(baseline_file).exists():
            baseline_path = baseline_file
            cleanup_baseline = False
            if debug:
                logger.debug(f"Using provided baseline file: {baseline_path}")
        elif generate_baseline:
            baseline_path = _generate_temp_baseline(filepath, arc_mode=arc_mode, debug=debug)
            cleanup_baseline = True
            if not baseline_path:
                logger.error("Baseline generation failed, falling back to refined estimation")
                # Fall through to refined estimation
                generate_baseline = False
                baseline_file = None
            else:
                if debug:
                    logger.debug(f"Generated temporary baseline: {baseline_path}")
        else:
            logger.error("baseline_file specified but does not exist, falling back to refined estimation")
            generate_baseline = False
            baseline_file = None
        
        # Calculate efficiency using baseline file comparison
        if baseline_path and (generate_baseline or baseline_file):
            try:
                baseline_size = Path(baseline_path).stat().st_size
                compressed_size = Path(filepath).stat().st_size
                
                if baseline_size > 0:
                    efficiency = (1 - (compressed_size / baseline_size)) * 100
                    
                    if debug:
                        logger.debug("\n  === Baseline File Comparison ===")
                        logger.debug(f"  Baseline file: {baseline_size:,} bytes")
                        logger.debug(f"  Compressed file: {compressed_size:,} bytes")
                        logger.debug(f"  Efficiency: {efficiency:.2f}%")
                    
                    # Cleanup temp baseline if needed
                    if cleanup_baseline:
                        try:
                            Path(baseline_path).unlink()
                            # Also remove temp directory if empty
                            temp_dir = Path(baseline_path).parent
                            if temp_dir.name.startswith("gttk_baseline_"):
                                temp_dir.rmdir()
                            if debug:
                                logger.debug(f"Cleaned up temporary baseline: {baseline_path}")
                        except Exception as e:
                            logger.warning(f"Could not cleanup temp baseline: {e}")
                    
                    return max(0.0, min(100.0, efficiency))
                else:
                    logger.error("Baseline file has zero size")
                    
            except Exception as e:
                logger.error(f"Error in baseline file comparison: {e}")
                if cleanup_baseline and baseline_path:
                    try:
                        Path(baseline_path).unlink()
                    except Exception:
                        pass
    
    # --- Refined Estimation Mode (Default, Production) ---
    name = Path(filepath).name
    try:
        tiff_parser = TiffTagParser(str(filepath), tiff_file=tiff)
    except Exception as e:
        logger.warning(f"Compression efficiency unknown for {name}: cannot read its TIFF structure ({e})")
        return None

    try:
        with tiff_parser:
            # Separate accumulators for compressible data vs. invariant overhead
            compressible_compressed_size = 0
            compressible_uncompressed_size = 0
            overhead_size = 0
            overhead_known = True
            has_compressed_data = False

            # File header overhead (8 bytes for classic TIFF, 16 for BigTIFF)
            is_bigtiff = tiff_parser.tif.is_bigtiff
            file_header_size = 16 if is_bigtiff else 8
            overhead_size += file_header_size

            if debug:
                logger.debug(f"Analyzing {len(tiff_parser.tif.pages)} IFDs in {name}")
                logger.debug(f"  File header: {file_header_size} bytes ({'BigTIFF' if is_bigtiff else 'Classic TIFF'})")

            # Iterate through ALL IFDs (main image + overviews + masks + thumbnails)
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

                    # Check if this is a transparency mask
                    is_mask = _is_transparency_mask_ifd(tags)

                    # Handle bit_count as tuple/list (multiple bands) or single value
                    if isinstance(bit_count, (list, tuple)):
                        total_bits_per_pixel = sum(bit_count) * band_count if band_count > len(bit_count) else sum(bit_count)
                    else:
                        total_bits_per_pixel = bit_count * band_count if bit_count else 8 * band_count

                    # Determine if tiled or striped for this IFD
                    tile_width_tag = tags.get(322)
                    tile_width = tile_width_tag.value if tile_width_tag else None
                    is_tiled = tile_width is not None

                    # Get actual compressed byte counts
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

                    if not byte_counts:
                        # An image IFD always carries strip or tile byte counts. Without
                        # them this IFD cannot be sized, and neither can the file.
                        logger.warning(f"Compression efficiency unknown for {name}: IFD {page_index} carries no byte counts")
                        return None

                    # Calculate actual compressed size for this IFD
                    if isinstance(byte_counts, (list, tuple, np.ndarray)):
                        actual_compressed_bytes = sum(int(b) for b in byte_counts)
                    else:
                        actual_compressed_bytes = int(byte_counts)

                    if is_mask:
                        # Transparency masks are ALWAYS compressed (DEFLATE) by GDAL
                        # Treat them as invariant overhead, not compressible data
                        overhead_size += actual_compressed_bytes

                        if debug:
                            logger.debug(f"  IFD {page_index} (Transparency Mask): "
                                         f"{width}x{height}, {total_bits_per_pixel}bpp, "
                                         f"{actual_compressed_bytes:,} bytes → overhead (always DEFLATE)")
                    else:
                        # This is compressible image data
                        theoretical_uncompressed = width * height * total_bits_per_pixel / 8

                        compressible_compressed_size += actual_compressed_bytes
                        compressible_uncompressed_size += theoretical_uncompressed

                        # Track if we found any actually compressed data
                        if compression_code != 1 and not (algo_interp and "uncompressed" in algo_interp.lower()):
                            has_compressed_data = True

                        if debug:
                            subfile_type_tag = tags.get(254)
                            subfile_type = subfile_type_tag.interpretation if subfile_type_tag else 'Image'
                            logger.debug(f"  IFD {page_index} ({subfile_type}): "
                                         f"{width}x{height}, {total_bits_per_pixel}bpp, "
                                         f"{actual_compressed_bytes:,} compressed / "
                                         f"{theoretical_uncompressed:,} uncompressed bytes")

                    # Add IFD header size to overhead. The overhead only informs the debug
                    # summary, so an unknown header does not make the figure unknown.
                    header_size = _estimate_ifd_header_size(page_index, tiff_parser.tif, tags)
                    if header_size is None:
                        overhead_known = False
                    else:
                        overhead_size += header_size
                        if debug:
                            logger.debug(f"    IFD {page_index} header/metadata: {header_size:,} bytes -> overhead")

                except Exception as e:
                    # One IFD that cannot be read makes the whole figure unknown: a number
                    # computed over the rest would be a plausible wrong answer.
                    logger.warning(f"Compression efficiency unknown for {name}: IFD {page_index} could not be sized ({e})")
                    return None

            if compressible_uncompressed_size == 0:
                logger.warning(f"Compression efficiency unknown for {name}: no image IFD could be sized")
                return None

            if not has_compressed_data:
                if debug:
                    logger.debug("  No compressed data found: an uncompressed file, efficiency 0.0")
                return 0.0

            # Calculate compression efficiency on compressible data only
            efficiency = (1 - (compressible_compressed_size / compressible_uncompressed_size)) * 100

            if debug:
                logger.debug("\n  === Compression Efficiency Summary ===")
                logger.debug(f"  Compressible data: {compressible_compressed_size:,} compressed / "
                             f"{compressible_uncompressed_size:,} uncompressed bytes")
                logger.debug(f"  Invariant overhead: {overhead_size:,} bytes"
                             + ("" if overhead_known else " (at least; one IFD header could not be sized)"))
                logger.debug(f"  Total file size: {compressible_compressed_size + overhead_size:,} bytes")
                logger.debug(f"  Efficiency: {efficiency:.2f}%")

            # Clamp to valid range [0, 100]
            return max(0.0, min(100.0, efficiency))

    except Exception as e:
        logger.warning(f"Compression efficiency unknown for {name}: {e}")
        return None


def compression_ratio(efficiency: Optional[float]) -> Optional[float]:
    """
    The size ratio an efficiency percentage implies: 50% -> 2.0.

    None when the efficiency is unknown, and at 100%, where the ratio is unbounded.

    Example:
        >>> compression_ratio(50.0), compression_ratio(0.0), compression_ratio(None)
        (2.0, 1.0, None)
    """
    if efficiency is None or efficiency >= 100:
        return None
    return 100 / (100 - efficiency)


def format_compression_efficiency(efficiency: Optional[float]) -> Tuple[str, str]:
    """
    The two report cells for an efficiency: ('45.20%', '1.82x'), or ('n/a', 'n/a').

    A report used to print an efficiency the calculation had not produced as 0.00% and
    1.00x, the same cells as a genuinely uncompressed file.

    Example:
        >>> format_compression_efficiency(45.2)
        ('45.20%', '1.82x')
        >>> format_compression_efficiency(None)
        ('n/a', 'n/a')
    """
    if efficiency is None:
        return ('n/a', 'n/a')
    ratio = compression_ratio(efficiency)
    return (f"{efficiency:.2f}%", f"{ratio:.2f}x" if ratio is not None else 'n/a')


def is_nodata_valid(nodata: float, dtype: str) -> bool:
    """
    Check if NoData value is within the valid range for the given data type.
    
    Args:
        nodata: The NoData value to validate
        dtype: The GDAL data type string (e.g., 'Float32', 'Int16', 'Byte')
        
    Returns:
        True if NoData value is valid for the data type, False otherwise
        
    Examples:
        >>> is_nodata_valid(-3.4e38, 'Float32')  # Representable: |x| < 3.4028235e38
        True
        >>> is_nodata_valid(-3.5e38, 'Float32')  # Out of range
        False
        >>> is_nodata_valid(np.nan, 'Float32')  # Valid for floats
        True
        >>> is_nodata_valid(-32768, 'Int16')  # Valid
        True
    """
    if np.isnan(nodata):
        # NaN is always valid for floating-point types
        return 'Float' in dtype
    
    if dtype == 'Float32':
        finfo = np.finfo(np.float32)
        # Suppress overflow warnings when comparing very large values
        with np.errstate(over='ignore', invalid='ignore'):
            try:
                return bool(abs(nodata) < finfo.max)
            except (OverflowError, TypeError):
                # Value too large for Float32
                return False
    elif dtype == 'Float64':
        finfo = np.finfo(np.float64)
        # Suppress overflow warnings when comparing very large values
        with np.errstate(over='ignore', invalid='ignore'):
            try:
                return bool(abs(nodata) < finfo.max)
            except (OverflowError, TypeError):
                # Value too large for Float64
                return False
    elif dtype == 'Int16':
        iinfo = np.iinfo(np.int16)
        return bool(iinfo.min <= nodata <= iinfo.max)
    elif dtype == 'Int32':
        iinfo = np.iinfo(np.int32)
        return bool(iinfo.min <= nodata <= iinfo.max)
    elif dtype == 'UInt16':
        # For unsigned types, explicitly check for negative values
        # and ensure value is within [0, 65535]
        if nodata < 0:
            return False
        iinfo = np.iinfo(np.uint16)
        return bool(nodata <= iinfo.max)
    elif dtype == 'UInt32':
        # For unsigned types, explicitly check for negative values
        if nodata < 0:
            return False
        iinfo = np.iinfo(np.uint32)
        return bool(nodata <= iinfo.max)
    elif dtype == 'Byte':
        # Byte is unsigned (0-255)
        if nodata < 0:
            return False
        iinfo = np.iinfo(np.uint8)
        return bool(nodata <= iinfo.max)
    
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
    
    # Try to get SRS
    srs = ds.GetSpatialRef()
    projection_info: Dict[str, Any] = {}
    used_json_fallback = False
    cached_projjson: Optional[str] = None
    
    # Fallback #1: If GetSpatialRef() fails, try using OSGeo4W Python bindings
    # This handles cases where ArcGIS Pro's GDAL can't parse modern EPSG codes
    if not srs:
        logger.info("GetSpatialRef() returned None, attempting OSGeo4W Python bindings fallback...")
        try:
            # Use direct Python bindings approach to get complete projection info, WKT, and PROJJSON
            projection_info_result, wkt_result, projjson_result = get_projection_info_from_osgeo4w(str(filepath))
            
            if projection_info_result:
                logger.info("Successfully retrieved projection info using OSGeo4W Python bindings")
                projection_info = projection_info_result
                used_json_fallback = True
                logger.info(f"Projection info from OSGeo4W: {projection_info}")
                
                # Create SRS from the WKT string for use in geographic_corners calculation
                if wkt_result:
                    try:
                        srs = osr.SpatialReference()
                        srs.ImportFromWkt(wkt_result)
                        logger.info("Created SRS object from OSGeo4W WKT")
                    except Exception as e_srs:
                        logger.debug(f"Could not create SRS from OSGeo4W WKT: {e_srs}")
                
                # Cache PROJJSON for later use (will be used by extract_projjson_string)
                if projjson_result:
                    cached_projjson = projjson_result
                    logger.info(f"Cached PROJJSON from OSGeo4W ({len(projjson_result)} chars)")
            else:
                logger.warning("OSGeo4W Python bindings fallback returned None")
        except Exception as e:
            logger.warning(f"OSGeo4W Python bindings fallback failed with exception: {e}")
            import traceback
            logger.warning(traceback.format_exc())
    
    # Try standard extraction if we haven't used JSON yet
    if srs and not used_json_fallback:
        projection_info = _retrieve_projection_info(ds, srs)
        
        # Fallback #2: If projection_info is incomplete (ArcGIS Pro without PROJ_LIB)
        # Check for missing unit names as indicator of broken PROJ environment
        is_incomplete = False
        
        # Check if we got meaningful CS type flags
        has_cs_type = (projection_info.get('is_geographic') or
                      projection_info.get('is_projected') or
                      projection_info.get('is_compound'))
        
        if has_cs_type:
            # If we know it's a geographic/projected/compound CS but missing unit names, it's incomplete
            if projection_info.get('is_projected') and not projection_info.get('linear_unit_name'):
                is_incomplete = True
                logger.debug("Projected CRS missing linear_unit_name; trying OSGeo4W fallback")
            elif projection_info.get('is_geographic'):
                if not projection_info.get('angular_unit_name'):
                    is_incomplete = True
                    logger.debug("Geographic CRS missing angular_unit_name; trying OSGeo4W fallback")
                
                # Check for 3D Geographic CRS (e.g. EPSG:4979) which should have a vertical unit
                if srs and srs.GetAxesCount() == 3:
                     # Verify if the 3rd axis is height/vertical
                     try:
                         axis_name = srs.GetAxisName(None, 2)
                         if axis_name and ('height' in axis_name.lower() or 'ellipsoid' in axis_name.lower()):
                             if not projection_info.get('vertical_unit_name'):
                                 is_incomplete = True
                                 logger.debug("3D Geographic CRS missing vertical unit; trying OSGeo4W fallback")
                     except Exception:
                         pass

            elif projection_info.get('is_compound'):
                # For compound, check if we're missing horizontal OR vertical unit names
                has_horiz_unit = projection_info.get('linear_unit_name') or projection_info.get('angular_unit_name')
                has_vert_unit = projection_info.get('vertical_unit_name')
                
                if not has_horiz_unit:
                    is_incomplete = True
                    logger.debug("Compound CRS missing horizontal unit names; trying OSGeo4W fallback")
                elif not has_vert_unit:
                    # Only consider it incomplete if we expected a vertical unit (i.e. it's compound)
                    is_incomplete = True
                    logger.debug("Compound CRS missing vertical unit names; trying OSGeo4W fallback")
        else:
            # SRS exists but CS type couldn't be determined — fall back to OSGeo4W for a full parse.
            logger.debug("SRS CS type not determined from initial parse; trying OSGeo4W fallback")
            is_incomplete = True

        if is_incomplete:
            logger.debug("projection_info incomplete, attempting OSGeo4W Python bindings fallback")
            try:
                # Use the new direct Python bindings approach to get complete info, WKT, and PROJJSON
                projection_info_result, wkt_result, projjson_result = get_projection_info_from_osgeo4w(str(filepath))
                if projection_info_result:
                    logger.info("Successfully retrieved complete projection info via OSGeo4W Python bindings")
                    # Replace with complete info from OSGeo4W
                    projection_info = projection_info_result
                    used_json_fallback = True
                    
                    # Update SRS if we got WKT and don't already have a good SRS
                    if wkt_result and srs:
                        try:
                            # Re-import with clean WKT from OSGeo4W
                            srs = osr.SpatialReference()
                            srs.ImportFromWkt(wkt_result)
                            logger.info("Updated SRS object from OSGeo4W WKT")
                        except Exception as e_srs:
                            logger.debug(f"Could not update SRS from OSGeo4W WKT: {e_srs}")
                    
                    # Cache PROJJSON for later use
                    if projjson_result:
                        cached_projjson = projjson_result
                        logger.info(f"Cached PROJJSON from OSGeo4W ({len(projjson_result)} chars)")
                else:
                    logger.warning("OSGeo4W Python bindings fallback returned None")
            except Exception as e:
                logger.warning(f"OSGeo4W Python bindings fallback failed: {e}")
    
    # Final fallback: Use GetProjection() WKT if still no SRS
    if not srs:
        wkt_string = ds.GetProjection()
        if wkt_string:
            try:
                srs = osr.SpatialReference(wkt=wkt_string)
            except Exception as e:
                logger.debug(f"Failed to create SRS from WKT: {e}")
                srs = None
        else:
            wkt_string = ''
    else:
        # If we got SRS, extract WKT from it
        try:
            wkt_string = srs.ExportToWkt() if srs else ''
        except Exception:
            wkt_string = ds.GetProjection()
    
    vert_srs = get_vertical_srs(ds)
    vert_srs_name = vert_srs.GetName() if vert_srs else None
    
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

    # Check if file is BigTIFF format
    is_bigtiff = False
    try:
        with tifffile.TiffFile(filepath) as tif:
            is_bigtiff = tif.is_bigtiff
    except Exception as e:
        logger.debug(f"Could not determine BigTIFF status: {e}")

    return GeoTiffInfo(
        filepath=filepath, x_size=ds.RasterXSize, y_size=ds.RasterYSize, bands=bands,
        wkt_string=wkt_string, geo_transform=gt, res_x=abs(gt[1]), res_y=abs(gt[5]), srs=srs,
        vertical_srs=vert_srs, vertical_srs_name=vert_srs_name, data_type=data_type,
        nodata=nodata_val, color_interp=color_interp_name, has_alpha=has_alpha_band,
        transparency_info=transparency_info, projection_info=projection_info,
        native_bbox=native_bbox, geographic_corners=geographic_corners,
        cached_projjson=cached_projjson, is_bigtiff=is_bigtiff
    )
