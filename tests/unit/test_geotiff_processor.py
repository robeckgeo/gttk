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
Unit Tests for geotiff_processor.py

Comprehensive test coverage for core GeoTIFF processing utilities including:
- Projection/SRS extraction and parsing
- Decimal precision detection
- Transparency detection (alpha, mask, NoData)
- Compression efficiency calculation
- NoData handling and validation
- Bounding box and corner calculations
- Error handling and edge cases

Target: >80% code coverage for geotiff_processor.py
"""

import pytest
import numpy as np
from osgeo import gdal, osr
import tempfile
import os

from gttk.utils.geotiff_processor import (
    # Precision detection functions
    _get_decimal_precision_for_value,
    calculate_precision_from_values,
    calculate_band_precision,
    determine_decimal_precision,
    
    # Transparency functions
    check_transparency,
    get_transparency_str,
    
    # NoData functions
    is_nodata_valid,
    remap_nodata_value,
    mask_nodata_value,
    
    # Projection functions
    _parse_json_projection_info,
    _retrieve_projection_info,
    _calculate_native_bbox,
    _calculate_geographic_corners,
    read_geotiff,
    
    # Compression functions
    get_uncompressed_size,
    calculate_compression_efficiency,
    _is_transparency_mask_ifd,
    
    # LERC/Quality functions
    get_lerc_max_z_error,
    estimate_image_quality,
)
from gttk.utils.data_models import GeoTiffInfo
from tests.fixtures.mock_geotiff_factory import MockGeoTIFF


# ==============================================================================
# FIXTURES
# ==============================================================================

@pytest.fixture
def mock_geotiff_basic():
    """Create basic MockGeoTIFF for testing."""
    mock = MockGeoTIFF(
        width=256,
        height=256,
        bands=1,
        data_type=gdal.GDT_Float32
    )
    return mock.to_gdal_dataset()


@pytest.fixture
def mock_geotiff_rgba():
    """Create RGBA MockGeoTIFF for transparency testing."""
    mock = MockGeoTIFF(
        width=256,
        height=256,
        bands=4,
        data_type=gdal.GDT_Byte
    )
    ds = mock.to_gdal_dataset()
    
    # Set color interpretations
    ds.GetRasterBand(1).SetColorInterpretation(gdal.GCI_RedBand)
    ds.GetRasterBand(2).SetColorInterpretation(gdal.GCI_GreenBand)
    ds.GetRasterBand(3).SetColorInterpretation(gdal.GCI_BlueBand)
    ds.GetRasterBand(4).SetColorInterpretation(gdal.GCI_AlphaBand)
    
    return ds


@pytest.fixture
def mock_geotiff_with_nodata():
    """Create MockGeoTIFF with NoData value."""
    mock = MockGeoTIFF(
        width=256,
        height=256,
        bands=1,
        data_type=gdal.GDT_Float32,
        nodata_value=-9999.0,
        nodata_pixel_count=100
    )
    return mock.to_gdal_dataset()


def create_test_float32_array(precision: int, shape: tuple = (100,)) -> np.ndarray:
    """
    Create test array with controlled decimal precision.
    
    Args:
        precision: Number of decimal places (0-7 for float32)
        shape: Array shape
        
    Returns:
        Float32 array with specified precision
    """
    data = np.random.uniform(100, 500, size=shape)
    return np.round(data, decimals=precision).astype(np.float32)


# ==============================================================================
# CATEGORY 1: PRECISION DETECTION TESTS
# ==============================================================================

class TestPrecisionDetection:
    """Test decimal precision detection functions."""
    
    def test_get_decimal_precision_integer_like(self):
        """Detect precision for integer-like float (e.g., 123.0 → 0)."""
        assert _get_decimal_precision_for_value(123.0, 7) == 0
        assert _get_decimal_precision_for_value(456.0, 7) == 0
        assert _get_decimal_precision_for_value(-789.0, 7) == 0
    
    def test_get_decimal_precision_one_decimal(self):
        """Detect 1 decimal place (e.g., 123.4 → 1)."""
        assert _get_decimal_precision_for_value(123.4, 7) == 1
        assert _get_decimal_precision_for_value(456.7, 7) == 1
        assert _get_decimal_precision_for_value(-789.1, 7) == 1
    
    def test_get_decimal_precision_two_decimals(self):
        """Detect 2 decimal places (e.g., 123.45 → 2)."""
        assert _get_decimal_precision_for_value(123.45, 7) == 2
        assert _get_decimal_precision_for_value(456.78, 7) == 2
        assert _get_decimal_precision_for_value(-789.12, 7) == 2
    
    def test_get_decimal_precision_three_decimals(self):
        """Detect 3 decimal places (e.g., 123.456 → 3)."""
        assert _get_decimal_precision_for_value(123.456, 7) == 3
        assert _get_decimal_precision_for_value(456.789, 7) == 3
    
    def test_get_decimal_precision_max_sigfigs(self):
        """Test with maximum significant figures."""
        # Float32 has ~7 significant figures
        value = 123.4567890  # More than 7 sigfigs
        precision = _get_decimal_precision_for_value(value, 7)
        assert precision <= 7
    
    def test_get_decimal_precision_nan(self):
        """Handle NaN values."""
        result = _get_decimal_precision_for_value(np.nan, 7)
        assert result == 0
    
    def test_get_decimal_precision_inf(self):
        """Handle infinity values."""
        assert _get_decimal_precision_for_value(np.inf, 7) == 0
        assert _get_decimal_precision_for_value(-np.inf, 7) == 0
    
    def test_calculate_precision_from_values_uniform(self):
        """Test array with uniform precision."""
        # All values have 2 decimal places
        values = np.array([123.45, 456.78, 789.12], dtype=np.float32)
        precision = calculate_precision_from_values(values, sigfigs=7)
        assert precision == 2
    
    def test_calculate_precision_from_values_mixed(self):
        """Test array with mixed precision (max wins)."""
        # Mix of 0, 1, and 3 decimal places
        values = np.array([123.0, 456.7, 789.123], dtype=np.float32)
        precision = calculate_precision_from_values(values, sigfigs=7)
        assert precision == 3  # Maximum precision
    
    def test_calculate_precision_from_values_with_nodata(self):
        """Test precision excluding NoData values."""
        values = np.array([123.45, -9999.0, 456.78, -9999.0, 789.12], dtype=np.float32)
        precision = calculate_precision_from_values(values, sigfigs=7, nodata=-9999.0)
        assert precision == 2  # NoData values excluded
    
    def test_calculate_precision_from_values_with_nan(self):
        """Test precision with NaN values."""
        values = np.array([123.45, np.nan, 456.78, np.nan], dtype=np.float32)
        precision = calculate_precision_from_values(values, sigfigs=7, nodata=np.nan)
        assert precision == 2  # NaN values excluded
    
    def test_calculate_precision_from_values_empty(self):
        """Handle empty array."""
        values = np.array([], dtype=np.float32)
        precision = calculate_precision_from_values(values, sigfigs=7)
        assert precision == 0
    
    def test_calculate_precision_from_values_all_nodata(self):
        """Handle array with all NoData values."""
        values = np.array([-9999.0, -9999.0, -9999.0], dtype=np.float32)
        precision = calculate_precision_from_values(values, sigfigs=7, nodata=-9999.0)
        assert precision == 0
    
    def test_calculate_band_precision_float32(self):
        """Test precision detection for Float32 band."""
        # Create mock dataset
        mock = MockGeoTIFF(
            width=100,
            height=100,
            bands=1,
            data_type=gdal.GDT_Float32,
            pixel_data=create_test_float32_array(2, (1, 100, 100))
        )
        ds = mock.to_gdal_dataset()
        band = ds.GetRasterBand(1)
        
        precision = calculate_band_precision(band, sample_size=10000)
        assert precision == 2
    
    def test_calculate_band_precision_integer_type(self):
        """Non-float types should return 0."""
        mock = MockGeoTIFF(
            width=100,
            height=100,
            bands=1,
            data_type=gdal.GDT_Byte
        )
        ds = mock.to_gdal_dataset()
        band = ds.GetRasterBand(1)
        
        precision = calculate_band_precision(band, sample_size=10000)
        assert precision == 0
    
    def test_determine_decimal_precision_single_band(self):
        """Test main entry point for single-band raster."""
        mock = MockGeoTIFF(
            width=100,
            height=100,
            bands=1,
            data_type=gdal.GDT_Float32,
            pixel_data=create_test_float32_array(3, (1, 100, 100))
        )
        ds = mock.to_gdal_dataset()
        
        precision = determine_decimal_precision(ds, sample_size=10000)
        assert isinstance(precision, int)
        assert precision == 3
    
    def test_determine_decimal_precision_multi_band(self):
        """Test main entry point for multi-band raster."""
        # Create bands with different precisions
        band1_data = create_test_float32_array(1, (100, 100))
        band2_data = create_test_float32_array(2, (100, 100))
        band3_data = create_test_float32_array(3, (100, 100))
        pixel_data = np.stack([band1_data, band2_data, band3_data])
        
        mock = MockGeoTIFF(
            width=100,
            height=100,
            bands=3,
            data_type=gdal.GDT_Float32,
            pixel_data=pixel_data
        )
        ds = mock.to_gdal_dataset()
        
        precision = determine_decimal_precision(ds, sample_size=10000)
        assert isinstance(precision, list)
        assert len(precision) == 3
        assert precision == [1, 2, 3]
    
    def test_determine_decimal_precision_empty_dataset(self):
        """Handle dataset with no bands."""
        driver = gdal.GetDriverByName('MEM')
        ds = driver.Create('', 100, 100, 0, gdal.GDT_Float32)
        
        precision = determine_decimal_precision(ds)
        assert precision == 0


# ==============================================================================
# CATEGORY 2: TRANSPARENCY DETECTION TESTS
# ==============================================================================

class TestTransparencyDetection:
    """Test transparency detection functions."""
    
    def test_check_transparency_no_transparency(self):
        """Dataset with no transparency."""
        mock = MockGeoTIFF(width=256, height=256, bands=3, data_type=gdal.GDT_Byte)
        ds = mock.to_gdal_dataset()
        
        transparency_info = check_transparency(ds)
        assert transparency_info == {}
    
    def test_check_transparency_alpha_band(self, mock_geotiff_rgba):
        """Dataset with alpha band."""
        transparency_info = check_transparency(mock_geotiff_rgba)
        assert 'Alpha' in transparency_info
        assert transparency_info['Alpha'] is True
    
    def test_check_transparency_nodata_integer(self):
        """Dataset with integer NoData value."""
        mock = MockGeoTIFF(
            width=256,
            height=256,
            bands=1,
            data_type=gdal.GDT_Int16,
            nodata_value=-9999
        )
        ds = mock.to_gdal_dataset()
        
        transparency_info = check_transparency(ds)
        assert 'NoData' in transparency_info
        assert transparency_info['NoData'] == '-9999'
    
    def test_check_transparency_nodata_float(self):
        """Dataset with float NoData value."""
        mock = MockGeoTIFF(
            width=256,
            height=256,
            bands=1,
            data_type=gdal.GDT_Float32,
            nodata_value=-9999.0
        )
        ds = mock.to_gdal_dataset()
        
        transparency_info = check_transparency(ds)
        assert 'NoData' in transparency_info
        assert '-9999' in transparency_info['NoData']
    
    def test_check_transparency_nodata_nan(self):
        """Dataset with NaN as NoData."""
        mock = MockGeoTIFF(
            width=256,
            height=256,
            bands=1,
            data_type=gdal.GDT_Float32,
            nodata_value=np.nan
        )
        ds = mock.to_gdal_dataset()
        
        transparency_info = check_transparency(ds)
        assert 'NoData' in transparency_info
        assert transparency_info['NoData'] == 'NaN'
    
    def test_check_transparency_no_bands(self):
        """Handle dataset with 0 bands."""
        driver = gdal.GetDriverByName('MEM')
        ds = driver.Create('', 256, 256, 0, gdal.GDT_Byte)
        
        transparency_info = check_transparency(ds)
        assert transparency_info == {}
    
    def test_get_transparency_str_no_transparency(self):
        """Format string for no transparency."""
        info = GeoTiffInfo(
            filepath='test.tif',
            x_size=256,
            y_size=256,
            bands=3,
            wkt_string='',
            geo_transform=(0, 1, 0, 0, 0, -1),
            res_x=1.0,
            res_y=1.0,
            transparency_info={}
        )
        result = get_transparency_str(info)
        assert result == 'No'
    
    def test_get_transparency_str_alpha_only(self):
        """Format string for alpha only."""
        info = GeoTiffInfo(
            filepath='test.tif',
            x_size=256,
            y_size=256,
            bands=4,
            wkt_string='',
            geo_transform=(0, 1, 0, 0, 0, -1),
            res_x=1.0,
            res_y=1.0,
            transparency_info={'Alpha': True}
        )
        result = get_transparency_str(info)
        assert result == 'Alpha'
    
    def test_get_transparency_str_nodata_only(self):
        """Format string for NoData only."""
        info = GeoTiffInfo(
            filepath='test.tif',
            x_size=256,
            y_size=256,
            bands=1,
            wkt_string='',
            geo_transform=(0, 1, 0, 0, 0, -1),
            res_x=1.0,
            res_y=1.0,
            transparency_info={'NoData': '-9999'}
        )
        result = get_transparency_str(info)
        assert result == 'NoData (-9999)'
    
    def test_get_transparency_str_combined(self):
        """Format string for combined transparency."""
        info = GeoTiffInfo(
            filepath='test.tif',
            x_size=256,
            y_size=256,
            bands=4,
            wkt_string='',
            geo_transform=(0, 1, 0, 0, 0, -1),
            res_x=1.0,
            res_y=1.0,
            transparency_info={
                'Alpha': True,
                'Mask': True,
                'NoData': 'NaN'
            }
        )
        result = get_transparency_str(info)
        assert 'Alpha' in result
        assert 'Mask' in result
        assert 'NoData' in result


# ==============================================================================
# CATEGORY 3: NODATA HANDLING TESTS
# ==============================================================================

class TestNoDataHandling:
    """Test NoData validation and conversion functions."""
    
    def test_is_nodata_valid_float32_valid(self):
        """Valid NoData for Float32."""
        assert is_nodata_valid(-9999.0, 'Float32') is True
        assert is_nodata_valid(0.0, 'Float32') is True
        assert is_nodata_valid(12345.67, 'Float32') is True
    
    def test_is_nodata_valid_float32_out_of_range(self):
        """Out-of-range NoData for Float32."""
        # Float32 max is ~3.4e38
        assert is_nodata_valid(-3.5e38, 'Float32') is False
        assert is_nodata_valid(3.5e38, 'Float32') is False
    
    def test_is_nodata_valid_float64_valid(self):
        """Valid NoData for Float64."""
        assert is_nodata_valid(-9999.0, 'Float64') is True
        assert is_nodata_valid(1.7e308, 'Float64') is True
    
    def test_is_nodata_valid_int16_valid(self):
        """Valid NoData for Int16."""
        assert is_nodata_valid(-32768, 'Int16') is True
        assert is_nodata_valid(32767, 'Int16') is True
        assert is_nodata_valid(0, 'Int16') is True
    
    def test_is_nodata_valid_int16_out_of_range(self):
        """Out-of-range NoData for Int16."""
        assert is_nodata_valid(-32769, 'Int16') is False
        assert is_nodata_valid(32768, 'Int16') is False
    
    def test_is_nodata_valid_uint16_valid(self):
        """Valid NoData for UInt16."""
        assert is_nodata_valid(0, 'UInt16') is True
        assert is_nodata_valid(65535, 'UInt16') is True
    
    def test_is_nodata_valid_uint16_out_of_range(self):
        """Out-of-range NoData for UInt16."""
        assert is_nodata_valid(-1, 'UInt16') is False
        assert is_nodata_valid(65536, 'UInt16') is False
    
    def test_is_nodata_valid_byte_valid(self):
        """Valid NoData for Byte."""
        assert is_nodata_valid(0, 'Byte') is True
        assert is_nodata_valid(255, 'Byte') is True
    
    def test_is_nodata_valid_nan_for_float(self):
        """NaN is valid for float types."""
        assert is_nodata_valid(np.nan, 'Float32') is True
        assert is_nodata_valid(np.nan, 'Float64') is True
    
    def test_is_nodata_valid_nan_for_integer(self):
        """NaN is not valid for integer types."""
        assert is_nodata_valid(np.nan, 'Int16') is False
        assert is_nodata_valid(np.nan, 'Byte') is False
    
    def test_remap_nodata_value_basic(self, mock_geotiff_with_nodata):
        """Remap NoData value in dataset."""
        # Original NoData is -9999.0, remap to -8888.0
        ds_remapped = remap_nodata_value(mock_geotiff_with_nodata, -9999.0, -8888.0)
        
        band = ds_remapped.GetRasterBand(1)
        array = band.ReadAsArray()
        
        # Check that -9999.0 no longer exists, replaced by -8888.0
        assert not np.any(array == -9999.0)
        assert np.any(array == -8888.0)
    
    def test_mask_nodata_value_creates_mask(self, mock_geotiff_with_nodata):
        """Convert NoData to transparency mask."""
        ds_masked = mask_nodata_value(mock_geotiff_with_nodata, -9999.0)
        
        # Check that NoData is unset
        band = ds_masked.GetRasterBand(1)
        assert band.GetNoDataValue() is None
        
        # Check that mask exists
        mask_band = band.GetMaskBand()
        mask_array = mask_band.ReadAsArray()
        
        # Mask should have 0 (transparent) where NoData was
        assert np.any(mask_array == 0)
        assert np.any(mask_array == 255)


# ==============================================================================
# CATEGORY 4: PROJECTION & SRS TESTS
# ==============================================================================

class TestProjectionExtraction:
    """Test projection/SRS extraction functions."""
    
    def test_parse_json_projection_info_geographic(self):
        """Parse geographic CRS from PROJJSON."""
        json_info = {
            'metadata': {'': {'AREA_OR_POINT': 'Area'}},
            'stac': {
                'proj:projjson': {
                    'type': 'GeographicCRS',
                    'name': 'WGS 84',
                    'id': {'code': '4326'},
                    'datum': {
                        'name': 'World Geodetic System 1984',
                        'ellipsoid': {
                            'name': 'WGS 84',
                            'semi_major_axis': 6378137.0,
                            'inverse_flattening': 298.257223563
                        }
                    },
                    'coordinate_system': {
                        'axis': [
                            {'name': 'Longitude', 'unit': 'degree'},
                            {'name': 'Latitude', 'unit': 'degree'}
                        ]
                    }
                }
            }
        }
        
        info = _parse_json_projection_info(json_info)
        
        assert info['is_geographic'] is True
        assert info['is_projected'] is False
        assert info['geographic_cs_name'] == 'WGS 84'
        assert info['geographic_cs_code'] == '4326'
        assert info['angular_unit_name'] == 'degree'
        assert info['raster_type'] == 'PixelIsArea'
    
    def test_parse_json_projection_info_projected(self):
        """Parse projected CRS from PROJJSON."""
        json_info = {
            'metadata': {'': {'AREA_OR_POINT': 'Point'}},
            'stac': {
                'proj:projjson': {
                    'type': 'ProjectedCRS',
                    'name': 'WGS 84 / UTM zone 10N',
                    'id': {'code': '32610'},
                    'base_crs': {
                        'name': 'WGS 84',
                        'id': {'code': '4326'}
                    },
                    'coordinate_system': {
                        'axis': [
                            {'name': 'Easting', 'unit': 'metre'},
                            {'name': 'Northing', 'unit': 'metre'}
                        ]
                    }
                }
            }
        }
        
        info = _parse_json_projection_info(json_info)
        
        assert info['is_projected'] is True
        assert info['is_geographic'] is False
        assert info['projected_cs_name'] == 'WGS 84 / UTM zone 10N'
        assert info['projected_cs_code'] == '32610'
        assert info['linear_unit_name'] == 'metre'
        assert info['raster_type'] == 'PixelIsPoint'
    
    def test_parse_json_projection_info_compound(self):
        """Parse compound CRS from PROJJSON."""
        json_info = {
            'metadata': {'': {}},
            'stac': {
                'proj:projjson': {
                    'type': 'CompoundCRS',
                    'name': 'WGS 84 + EGM96 height',
                    'components': [
                        {
                            'type': 'GeographicCRS',
                            'name': 'WGS 84'
                        },
                        {
                            'type': 'VerticalCRS',
                            'name': 'EGM96 height',
                            'id': {'code': '5773'},
                            'datum': {'name': 'EGM96 geoid'},
                            'coordinate_system': {
                                'axis': [{'unit': 'metre'}]
                            }
                        }
                    ]
                }
            }
        }
        
        info = _parse_json_projection_info(json_info)
        
        assert info['is_compound'] is True
        assert info['vertical_cs_name'] == 'EGM96 height'
        assert info['vertical_cs_code'] == '5773'
        assert info['vertical_unit_name'] == 'metre'
    
    def test_retrieve_projection_info_wgs84(self):
        """Extract WGS 84 projection info from SRS."""
        # Create WGS 84 SRS
        srs = osr.SpatialReference()
        srs.ImportFromEPSG(4326)
        
        # Create mock dataset
        driver = gdal.GetDriverByName('MEM')
        ds = driver.Create('', 256, 256, 1, gdal.GDT_Byte)
        ds.SetProjection(srs.ExportToWkt())
        
        info = _retrieve_projection_info(ds, srs)
        
        assert info['is_geographic'] is True
        assert info['is_projected'] is False
        assert 'WGS' in info['geographic_cs_name']
        assert info['geographic_cs_code'] == '4326'
    
    def test_retrieve_projection_info_utm(self):
        """Extract UTM projected CRS info from SRS."""
        # Create UTM Zone 10N SRS
        srs = osr.SpatialReference()
        srs.ImportFromEPSG(32610)
        
        # Create mock dataset
        driver = gdal.GetDriverByName('MEM')
        ds = driver.Create('', 256, 256, 1, gdal.GDT_Byte)
        ds.SetProjection(srs.ExportToWkt())
        
        info = _retrieve_projection_info(ds, srs)
        
        assert info['is_projected'] is True
        assert info['projected_cs_code'] == '32610'
        assert 'metre' in info['linear_unit_name'].lower()
    
    def test_calculate_native_bbox_pixel_is_area(self):
        """Calculate bbox for PixelIsArea raster."""
        # Create mock dataset with known geotransform
        driver = gdal.GetDriverByName('MEM')
        ds = driver.Create('', 100, 100, 1, gdal.GDT_Byte)
        
        # Geotransform: origin at (1000, 2000), 10m pixels, north-up
        gt = (1000.0, 10.0, 0.0, 2000.0, 0.0, -10.0)
        ds.SetGeoTransform(gt)
        
        projection_info = {'raster_type': 'PixelIsArea'}
        bbox = _calculate_native_bbox(ds, gt, projection_info)
        
        # For PixelIsArea: extents are at outer edges
        assert bbox['west'] == 1000.0
        assert bbox['east'] == 2000.0  # 1000 + 100*10
        assert bbox['north'] == 2000.0
        assert bbox['south'] == 1000.0  # 2000 + 100*(-10)
    
    def test_calculate_native_bbox_pixel_is_point(self):
        """Calculate bbox for PixelIsPoint raster."""
        # Create mock dataset
        driver = gdal.GetDriverByName('MEM')
        ds = driver.Create('', 100, 100, 1, gdal.GDT_Byte)
        
        gt = (1000.0, 10.0, 0.0, 2000.0, 0.0, -10.0)
        ds.SetGeoTransform(gt)
        
        projection_info = {'raster_type': 'PixelIsPoint'}
        bbox = _calculate_native_bbox(ds, gt, projection_info)
        
        # For PixelIsPoint: extents adjusted by half pixel
        assert bbox['west'] == 1005.0  # 1000 + 5 (half pixel)
        assert bbox['east'] == 1995.0  # 2000 - 5
        assert bbox['north'] == 1995.0  # 2000 - 5
        assert bbox['south'] == 1005.0  # 1000 + 5
    
    def test_calculate_geographic_corners_geographic_crs(self):
        """Calculate corners for geographic CRS (no transform needed)."""
        # Create WGS 84 dataset
        srs = osr.SpatialReference()
        srs.ImportFromEPSG(4326)
        
        driver = gdal.GetDriverByName('MEM')
        ds = driver.Create('', 100, 100, 1, gdal.GDT_Byte)
        ds.SetProjection(srs.ExportToWkt())
        
        # Geographic coordinates (degrees)
        gt = (-180.0, 1.0, 0.0, 90.0, 0.0, -1.0)
        ds.SetGeoTransform(gt)
        
        projection_info = {'raster_type': 'PixelIsArea'}
        corners = _calculate_geographic_corners(ds, srs, gt, projection_info)
        
        assert corners is not None
        assert 'Upper Left' in corners
        assert 'Center' in corners
        # For geographic CRS, native coords = geographic coords
        assert corners['Upper Left'][0] == -180.0  # longitude
        assert corners['Upper Left'][1] == 90.0    # latitude
    
    def test_calculate_geographic_corners_projected_crs(self):
        """Calculate corners for projected CRS (transform to WGS84)."""
        # Create UTM Zone 10N dataset
        srs = osr.SpatialReference()
        srs.ImportFromEPSG(32610)
        
        driver = gdal.GetDriverByName('MEM')
        ds = driver.Create('', 100, 100, 1, gdal.GDT_Byte)
        ds.SetProjection(srs.ExportToWkt())
        
        # UTM coordinates (meters)
        gt = (500000.0, 100.0, 0.0, 4500000.0, 0.0, -100.0)
        ds.SetGeoTransform(gt)
        
        projection_info = {'raster_type': 'PixelIsArea'}
        corners = _calculate_geographic_corners(ds, srs, gt, projection_info)
        
        assert corners is not None
        assert 'Upper Left' in corners
        # Corners should be in geographic coordinates (lon/lat)
        lon, lat = corners['Upper Left']
        assert -180 < lon < 180  # Valid longitude
        assert -90 < lat < 90     # Valid latitude
    
    def test_read_geotiff_basic(self, tmp_path):
        """Test main read_geotiff() orchestrator."""
        # Create simple GeoTIFF with WGS 84 as actual file
        filepath = tmp_path / "test.tif"
        srs = osr.SpatialReference()
        srs.ImportFromEPSG(4326)
        
        driver = gdal.GetDriverByName('GTiff')
        ds = driver.Create(str(filepath), 256, 256, 1, gdal.GDT_Float32)
        ds.SetProjection(srs.ExportToWkt())
        ds.SetGeoTransform((0.0, 1.0, 0.0, 0.0, 0.0, -1.0))
        
        # Set NoData value
        band = ds.GetRasterBand(1)
        band.SetNoDataValue(-9999.0)
        ds.FlushCache()
        ds = None
        
        # Reopen and test
        ds = gdal.Open(str(filepath))
        info = read_geotiff(ds)
        ds = None
        
        assert isinstance(info, GeoTiffInfo)
        assert info.x_size == 256
        assert info.y_size == 256
        assert info.bands == 1
        assert info.data_type == 'Float32'
        assert info.nodata == -9999.0
        assert info.projection_info is not None
        assert info.native_bbox is not None
        assert info.geographic_corners is not None


# ==============================================================================
# CATEGORY 5: COMPRESSION EFFICIENCY TESTS
# ==============================================================================

class TestCompressionEfficiency:
    """Test compression efficiency calculation."""
    
    def test_get_uncompressed_size_single_ifd(self):
        """Calculate uncompressed size for single IFD."""
        # Create test GeoTIFF
        fd, filename = tempfile.mkstemp(suffix='.tif')
        os.close(fd)
        
        try:
            # Create 256x256 Byte image (3 bands)
            driver = gdal.GetDriverByName('GTiff')
            ds = driver.Create(filename, 256, 256, 3, gdal.GDT_Byte, options=['COMPRESS=NONE'])
            ds = None  # Close to write
            
            uncompressed_size = get_uncompressed_size(filename)
            
            # Expected: 256 * 256 * 3 bytes = 196,608 bytes
            expected_size = 256 * 256 * 3
            assert uncompressed_size == expected_size
        finally:
            if os.path.exists(filename):
                os.remove(filename)
    
    def test_get_uncompressed_size_with_overviews(self):
        """Calculate uncompressed size including overviews."""
        fd, filename = tempfile.mkstemp(suffix='.tif')
        os.close(fd)
        
        try:
            # Create 512x512 Byte image with overview
            driver = gdal.GetDriverByName('GTiff')
            ds = driver.Create(filename, 512, 512, 1, gdal.GDT_Byte, options=['COMPRESS=NONE'])
            ds.BuildOverviews('NEAREST', [2])  # 256x256 overview
            ds = None
            
            uncompressed_size = get_uncompressed_size(filename)
            
            # Main: 512*512 = 262,144
            # Overview: 256*256 = 65,536
            # Total = 327,680
            expected_size = 512 * 512 + 256 * 256
            assert uncompressed_size == expected_size
        finally:
            if os.path.exists(filename):
                os.remove(filename)
    
    def test_is_transparency_mask_ifd(self):
        """Detect transparency mask IFDs."""
        from gttk.utils.tiff_tag_parser import TiffTag
        
        # Create tags for a transparency mask IFD
        # Photometric=4 (TransparencyMask), BitsPerSample=1
        mask_tags = {
            262: TiffTag(262, 'PhotometricInterpretation', 4, '4 (TransparencyMask)'),
            258: TiffTag(258, 'BitsPerSample', 1, None)
        }
        
        assert _is_transparency_mask_ifd(mask_tags) is True
        
        # Non-mask IFD (Photometric=2 RGB)
        image_tags = {
            262: TiffTag(262, 'PhotometricInterpretation', 2, '2 (RGB)'),
            258: TiffTag(258, 'BitsPerSample', 8, None)
        }
        
        assert _is_transparency_mask_ifd(image_tags) is False
    
    def test_calculate_compression_efficiency_uncompressed(self):
        """Uncompressed file should return 0%."""
        fd, filename = tempfile.mkstemp(suffix='.tif')
        os.close(fd)
        
        try:
            driver = gdal.GetDriverByName('GTiff')
            ds = driver.Create(filename, 256, 256, 1, gdal.GDT_Byte, options=['COMPRESS=NONE'])
            ds = None
            
            efficiency = calculate_compression_efficiency(filename)
            
            # Uncompressed should have 0% efficiency
            assert efficiency == 0.0
        finally:
            if os.path.exists(filename):
                os.remove(filename)
    
    def test_calculate_compression_efficiency_deflate(self):
        """Test efficiency calculation for DEFLATE compression."""
        fd, filename = tempfile.mkstemp(suffix='.tif')
        os.close(fd)
        
        try:
            # Create image with DEFLATE compression
            driver = gdal.GetDriverByName('GTiff')
            ds = driver.Create(
                filename, 256, 256, 1, gdal.GDT_Byte,
                options=['COMPRESS=DEFLATE', 'PREDICTOR=2']
            )
            # Write some data (zeros compress well)
            band = ds.GetRasterBand(1)
            data = np.zeros((256, 256), dtype=np.uint8)
            band.WriteArray(data)
            ds = None
            
            efficiency = calculate_compression_efficiency(filename)
            
            # Zeros should compress very well (>50%)
            assert efficiency > 50.0
            assert efficiency <= 100.0
        finally:
            if os.path.exists(filename):
                os.remove(filename)
    
    def test_calculate_compression_efficiency_lzw(self):
        """Test efficiency calculation for LZW compression."""
        fd, filename = tempfile.mkstemp(suffix='.tif')
        os.close(fd)
        
        try:
            driver = gdal.GetDriverByName('GTiff')
            ds = driver.Create(
                filename, 256, 256, 1, gdal.GDT_Byte,
                options=['COMPRESS=LZW']
            )
            # Random data (doesn't compress as well)
            band = ds.GetRasterBand(1)
            data = np.random.randint(0, 256, (256, 256), dtype=np.uint8)
            band.WriteArray(data)
            ds = None
            
            efficiency = calculate_compression_efficiency(filename)
            
            # Random data compresses poorly, but should still have some effect
            assert 0.0 <= efficiency <= 100.0
        finally:
            if os.path.exists(filename):
                os.remove(filename)
    
    def test_calculate_compression_efficiency_with_mask(self):
        """Handle transparency mask IFDs correctly."""
        fd, filename = tempfile.mkstemp(suffix='.tif')
        os.close(fd)
        
        try:
            # Create image with internal mask
            driver = gdal.GetDriverByName('GTiff')
            ds = driver.Create(
                filename, 256, 256, 1, gdal.GDT_Byte,
                options=['COMPRESS=DEFLATE']
            )
            # Create mask
            band = ds.GetRasterBand(1)
            band.CreateMaskBand(gdal.GMF_PER_DATASET)
            ds = None
            
            # Should handle mask IFD without errors
            efficiency = calculate_compression_efficiency(filename)
            
            assert 0.0 <= efficiency <= 100.0
        finally:
            if os.path.exists(filename):
                os.remove(filename)
    
    def test_calculate_compression_efficiency_with_overviews(self):
        """Account for overview IFDs in calculation."""
        fd, filename = tempfile.mkstemp(suffix='.tif')
        os.close(fd)
        
        try:
            # Create image with overviews
            driver = gdal.GetDriverByName('GTiff')
            ds = driver.Create(
                filename, 512, 512, 1, gdal.GDT_Byte,
                options=['COMPRESS=DEFLATE', 'TILED=YES']
            )
            ds.BuildOverviews('NEAREST', [2, 4])
            ds = None
            
            efficiency = calculate_compression_efficiency(filename)
            
            # Should include all IFDs in calculation
            assert 0.0 <= efficiency <= 100.0
        finally:
            if os.path.exists(filename):
                os.remove(filename)


# ==============================================================================
# CATEGORY 6: LERC & QUALITY TESTS
# ==============================================================================

class TestLERCAndQuality:
    """Test LERC and quality estimation."""
    
    def test_estimate_image_quality_jxl_lossless(self):
        """JXL lossless should return '100 (Lossless)'."""
        # Create mock dataset with JXL_LOSSLESS metadata
        driver = gdal.GetDriverByName('MEM')
        ds = driver.Create('', 256, 256, 3, gdal.GDT_Byte)
        ds.SetMetadataItem("JXL_LOSSLESS", "YES", "IMAGE_STRUCTURE")
        
        quality = estimate_image_quality(ds, "JXL")
        assert quality == "100 (Lossless)"
    
    def test_estimate_image_quality_jxl_lossy(self):
        """Estimate JXL quality from JXL_DISTANCE."""
        driver = gdal.GetDriverByName('MEM')
        ds = driver.Create('', 256, 256, 3, gdal.GDT_Byte)
        # Distance of 1.0 should estimate quality ~90
        ds.SetMetadataItem("JXL_DISTANCE", "1.0", "IMAGE_STRUCTURE")
        
        quality = estimate_image_quality(ds, "JXL")
        assert "(Est.)" in quality
        # Distance 1.0 = quality ~90 (100 - 1.0/0.1)
        assert "90" in quality
    
    def test_estimate_image_quality_jpeg_no_metadata(self):
        """JPEG quality not preserved in metadata, return N/A."""
        driver = gdal.GetDriverByName('MEM')
        ds = driver.Create('', 256, 256, 3, gdal.GDT_Byte)
        
        quality = estimate_image_quality(ds, "JPEG")
        assert quality == "N/A"
    
    def test_get_lerc_max_z_error_from_metadata(self):
        """Extract LERC max_z_error from dataset metadata."""
        fd, filename = tempfile.mkstemp(suffix='.tif')
        os.close(fd)
        
        try:
            # Create LERC-compressed file
            driver = gdal.GetDriverByName('GTiff')
            ds = driver.Create(
                filename, 256, 256, 1, gdal.GDT_Float32,
                options=['COMPRESS=LERC', 'MAX_Z_ERROR=0.01']
            )
            band = ds.GetRasterBand(1)
            data = np.random.uniform(100, 500, (256, 256)).astype(np.float32)
            band.WriteArray(data)
            ds = None
            
            # Reopen and check
            ds = gdal.Open(filename)
            z_error = get_lerc_max_z_error(ds)
            
            # Should extract the MAX_Z_ERROR value
            assert z_error != ''
            if z_error:  # May not be available on all GDAL versions
                assert float(z_error) >= 0
            ds = None
        finally:
            if os.path.exists(filename):
                os.remove(filename)


# ==============================================================================
# CATEGORY 7: ERROR HANDLING & EDGE CASES
# ==============================================================================

class TestErrorHandlingAndEdgeCases:
    """Test error handling and edge cases."""
    
    def test_check_transparency_no_bands(self):
        """Handle dataset with 0 bands."""
        driver = gdal.GetDriverByName('MEM')
        ds = driver.Create('', 256, 256, 0, gdal.GDT_Byte)
        
        transparency_info = check_transparency(ds)
        assert transparency_info == {}
    
    def test_calculate_precision_none_values(self):
        """Handle None/empty arrays in precision calculation."""
        # Empty array
        precision = calculate_precision_from_values(np.array([]), sigfigs=7)
        assert precision == 0
    
    def test_calculate_native_bbox_no_geotransform(self):
        """Handle dataset without geotransform."""
        driver = gdal.GetDriverByName('MEM')
        ds = driver.Create('', 256, 256, 1, gdal.GDT_Byte)
        
        projection_info = {'raster_type': 'PixelIsArea'}
        # None geotransform should return empty dict
        bbox = _calculate_native_bbox(ds, None, projection_info)  # type: ignore
        assert bbox == {}
    
    def test_calculate_geographic_corners_no_srs(self):
        """Handle dataset without spatial reference."""
        driver = gdal.GetDriverByName('MEM')
        ds = driver.Create('', 256, 256, 1, gdal.GDT_Byte)
        gt = (0.0, 1.0, 0.0, 0.0, 0.0, -1.0)
        
        projection_info = {'raster_type': 'PixelIsArea'}
        corners = _calculate_geographic_corners(ds, None, gt, projection_info)  # type: ignore
        assert corners is None
    
    def test_is_nodata_valid_unknown_dtype(self):
        """Handle unknown data type gracefully."""
        # Unknown dtype should return True (assume valid)
        result = is_nodata_valid(-9999.0, 'UnknownType')
        assert result is True
    
    def test_get_uncompressed_size_corrupted_file(self):
        """Handle corrupted/invalid file gracefully."""
        fd, filename = tempfile.mkstemp(suffix='.tif')
        os.close(fd)
        
        try:
            # Write garbage data
            with open(filename, 'wb') as f:
                f.write(b'not a tiff file')
            
            size = get_uncompressed_size(filename)
            # Unknown, not a size: 0.0 is not a size any raster has
            assert size is None
        finally:
            if os.path.exists(filename):
                os.remove(filename)
    
    def test_calculate_compression_efficiency_invalid_file(self):
        """Handle invalid file path gracefully."""
        # Non-existent file
        efficiency = calculate_compression_efficiency('/nonexistent/file.tif')
        assert efficiency is None   # unknown, not "uncompressed"
    
    def test_read_geotiff_no_projection(self, tmp_path):
        """Handle dataset without projection info."""
        filepath = tmp_path / "test_no_proj.tif"
        driver = gdal.GetDriverByName('GTiff')
        ds = driver.Create(str(filepath), 256, 256, 1, gdal.GDT_Byte)
        # Don't set projection
        ds.FlushCache()
        ds = None
        
        # Reopen and test
        ds = gdal.Open(str(filepath))
        info = read_geotiff(ds)
        ds = None
        
        assert isinstance(info, GeoTiffInfo)
        assert info.x_size == 256
        assert info.y_size == 256
        # Should handle missing projection gracefully
        assert info.wkt_string == ''
    
    def test_remap_nodata_no_matching_pixels(self):
        """Handle remapping when no pixels match source NoData."""
        mock = MockGeoTIFF(
            width=100,
            height=100,
            bands=1,
            data_type=gdal.GDT_Float32,
            nodata_value=None  # No NoData pixels
        )
        ds = mock.to_gdal_dataset()
        
        # Try to remap non-existent NoData value
        ds_remapped = remap_nodata_value(ds, -9999.0, -8888.0)
        
        # Should complete without error
        assert ds_remapped is not None


if __name__ == "__main__":
    pytest.main([__file__, "-v"])
