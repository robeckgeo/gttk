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
Pytest configuration and shared fixtures for GTTK test suite.

This module provides:
- Pytest configuration (markers, options)
- Shared fixtures for common test data
- Test utility functions
- Mock data factories

Fixtures are organized by scope:
- session: Created once per test session (expensive setup)
- module: Created once per test module
- function: Created for each test function (default)

Example:
    >>> def test_using_fixture(mock_geotiff):
    ...     '''Test using the mock_geotiff fixture.'''
    ...     assert mock_geotiff.width == 256
"""

import pytest
import numpy as np
from osgeo import gdal, osr
from typing import Optional, Tuple

# Import our mock factories
# pythonpath is configured in pytest.ini to include project root
from tests.fixtures.mock_geotiff_factory import MockGeoTIFF


# =============================================================================
# Pytest Configuration
# =============================================================================

def pytest_configure(config):
    """
    Configure pytest with custom markers and options.
    
    Markers defined in pytest.ini are registered here for documentation.
    """
    # Markers are defined in pytest.ini, but we can add dynamic configuration here
    pass


def pytest_assertrepr_compare(op, left, right):
    """
    Custom assertion representation to prevent base64 histograms from flooding logs.
    
    This hook intercepts assertion comparisons and truncates very long strings
    (like base64-encoded histogram data) to keep test output readable.
    
    Args:
        op: Comparison operator ('==', '!=', 'in', etc.)
        left: Left operand of comparison
        right: Right operand of comparison
        
    Returns:
        List of strings for assertion message, or None for default behavior
    """
    # Define max length before truncation
    MAX_STRING_LENGTH = 500
    
    def truncate_if_needed(value):
        """Truncate string if it's too long."""
        if isinstance(value, str) and len(value) > MAX_STRING_LENGTH:
            # Check if it looks like base64 (contains mostly alphanumeric + / =)
            base64_chars = sum(c.isalnum() or c in '/+=' for c in value[:100])
            if base64_chars > 80:  # If >80% of first 100 chars are base64-like
                return f"<base64 string, length={len(value)} (truncated for readability)>"
            else:
                return value[:MAX_STRING_LENGTH] + f"... (truncated, total length={len(value)})"
        return value
    
    # Only customize for string comparisons
    if isinstance(left, str) or isinstance(right, str):
        left_repr = truncate_if_needed(left)
        right_repr = truncate_if_needed(right)
        
        if left_repr != left or right_repr != right:
            return [
                "Comparing strings:",
                f"  left: {left_repr}",
                f"  {op}",
                f"  right: {right_repr}",
            ]
    
    # Return None to use default pytest behavior
    return None


# =============================================================================
# Session-scope Fixtures (Created once per test session)
# =============================================================================

@pytest.fixture(scope="session")
def temp_dir(tmp_path_factory):
    """
    Create a temporary directory for the entire test session.
    
    This directory persists for all tests in the session and is cleaned up
    automatically by pytest after all tests complete.
    
    Returns:
        Path: Path to temporary directory
        
    Example:
        >>> def test_file_creation(temp_dir):
        ...     test_file = temp_dir / "test.tif"
        ...     # Create file...
        ...     assert test_file.exists()
    """
    return tmp_path_factory.mktemp("gttk_tests")


# =============================================================================
# Module-scope Fixtures (Created once per test module)
# =============================================================================

@pytest.fixture(scope="module")
def sample_wkt_geographic():
    """
    WKT string for WGS 84 geographic coordinate system.
    
    Returns:
        str: WKT2_2019 format string for EPSG:4326
    """
    srs = osr.SpatialReference()
    srs.ImportFromEPSG(4326)
    return srs.ExportToWkt()


@pytest.fixture(scope="module")
def sample_wkt_projected():
    """
    WKT string for UTM Zone 10N projected coordinate system.
    
    Returns:
        str: WKT2_2019 format string for EPSG:32610
    """
    srs = osr.SpatialReference()
    srs.ImportFromEPSG(32610)
    return srs.ExportToWkt()


@pytest.fixture(scope="module")
def sample_wkt_compound():
    """
    WKT string for compound coordinate system (UTM + vertical).
    
    Returns:
        str: WKT2_2019 format string for EPSG:32610+5703
    """
    srs = osr.SpatialReference()
    srs.SetFromUserInput("EPSG:32610+5703")
    return srs.ExportToWkt()


# =============================================================================
# Function-scope Fixtures (Created for each test)
# =============================================================================

@pytest.fixture
def mock_geotiff_basic():
    """
    Create a basic mock GeoTIFF for testing.
    
    Creates a simple 256x256 single-band Float32 GeoTIFF with WGS84 projection.
    This is the most common test case.
    
    Returns:
        MockGeoTIFF: Configured mock GeoTIFF object
        
    Example:
        >>> def test_basic_operations(mock_geotiff_basic):
        ...     ds = mock_geotiff_basic.to_gdal_dataset()
        ...     assert ds.RasterXSize == 256
    """
    return MockGeoTIFF(
        width=256,
        height=256,
        bands=1,
        data_type=gdal.GDT_Float32,
        crs='EPSG:4326',
        compression='NONE'
    )


@pytest.fixture
def mock_geotiff_multiband():
    """
    Create a 3-band RGB mock GeoTIFF for testing.
    
    Returns:
        MockGeoTIFF: Configured mock GeoTIFF with 3 bands
    """
    return MockGeoTIFF(
        width=512,
        height=512,
        bands=3,
        data_type=gdal.GDT_Byte,
        crs='EPSG:32610',
        compression='DEFLATE',
        predictor=2
    )


@pytest.fixture
def mock_geotiff_with_nodata():
    """
    Create a mock GeoTIFF with NoData values for testing.
    
    Returns:
        MockGeoTIFF: Configured mock GeoTIFF with NoData
    """
    return MockGeoTIFF(
        width=100,
        height=100,
        bands=1,
        data_type=gdal.GDT_Float32,
        crs='EPSG:32610',
        nodata_value=-9999.0,
        nodata_pixel_count=42  # Exactly 42 NoData pixels for testing
    )


@pytest.fixture
def mock_geotiff_compressed():
    """
    Create a compressed mock GeoTIFF for testing compression functions.
    
    Returns:
        MockGeoTIFF: Configured mock GeoTIFF with DEFLATE compression
    """
    return MockGeoTIFF(
        width=512,
        height=512,
        bands=1,
        data_type=gdal.GDT_Float32,
        crs='EPSG:32610',
        compression='DEFLATE',
        predictor=3,
        tiled=True,
        tile_size=256
    )


@pytest.fixture
def mock_geotiff_dem():
    """
    Create a mock DEM (elevation model) for testing.
    
    Returns:
        MockGeoTIFF: Configured mock DEM with compound CRS
    """
    return MockGeoTIFF(
        width=1024,
        height=1024,
        bands=1,
        data_type=gdal.GDT_Float32,
        crs='EPSG:32610+5703',  # UTM + NAVD88 vertical
        nodata_value=-9999.0,
        compression='ZSTD',
        predictor=3
    )


@pytest.fixture
def sample_tiff_tags():
    """
    Create a sample list of TiffTag objects for testing.
    
    Returns:
        List[TiffTag]: Common TIFF tags
    """
    from gttk.utils.data_models import TiffTag
    
    return [
        TiffTag(code=256, name="ImageWidth", value=1024),
        TiffTag(code=257, name="ImageLength", value=768),
        TiffTag(code=258, name="BitsPerSample", value=8),
        TiffTag(code=259, name="Compression", value=5, interpretation="LZW"),
        TiffTag(code=262, name="PhotometricInterpretation", value=2, interpretation="RGB"),
        TiffTag(code=273, name="StripOffsets", value=[100, 200, 300]),
        TiffTag(code=277, name="SamplesPerPixel", value=3),
        TiffTag(code=278, name="RowsPerStrip", value=256),
    ]


@pytest.fixture
def sample_geokeys():
    """
    Create a sample list of GeoKey objects for testing.
    
    Returns:
        List[GeoKey]: Common GeoKeys for projected CRS
    """
    from gttk.utils.data_models import GeoKey
    
    return [
        GeoKey(
            id=1024,
            name="GTModelTypeGeoKey",
            value=1,
            value_text="1 (ModelTypeProjected)",
            location=0,
            count=1
        ),
        GeoKey(
            id=1025,
            name="GTRasterTypeGeoKey",
            value=1,
            value_text="1 (RasterPixelIsArea)",
            location=0,
            count=1
        ),
        GeoKey(
            id=3072,
            name="ProjectedCRSGeoKey",
            value=32610,
            value_text="32610 (WGS 84 / UTM zone 10N)",
            location=0,
            count=1
        ),
    ]


@pytest.fixture
def sample_statistics():
    """
    Create sample StatisticsBand objects for testing.
    
    Returns:
        List[StatisticsBand]: Statistics for a 3-band image
    """
    from gttk.utils.data_models import StatisticsBand
    
    return [
        StatisticsBand(
            band_name="Band 1",
            valid_percent=99.5,
            valid_count=65000,
            mask_count=0,
            alpha_0_count=0,
            nodata_count=36,
            nodata_value=-9999.0,
            minimum=0.0,
            maximum=255.0,
            mean=127.5,
            std_dev=45.3,
            median=128.0
        ),
        StatisticsBand(
            band_name="Band 2",
            valid_percent=99.5,
            valid_count=65000,
            mask_count=0,
            alpha_0_count=0,
            nodata_count=36,
            minimum=0.0,
            maximum=255.0,
            mean=130.2,
            std_dev=42.1,
            median=131.0
        ),
        StatisticsBand(
            band_name="Band 3",
            valid_percent=99.5,
            valid_count=65000,
            mask_count=0,
            alpha_0_count=0,
            nodata_count=36,
            minimum=0.0,
            maximum=255.0,
            mean=125.8,
            std_dev=47.5,
            median=126.0
        ),
    ]


# =============================================================================
# Utility Functions
# =============================================================================

def create_synthetic_elevation_data(
    size: int,
    decimals: int,
    value_range: Tuple[float, float] = (100.0, 200.0),
    nodata_value: Optional[float] = None,
    nodata_count: int = 0
) -> np.ndarray:
    """
    Create synthetic elevation data with controlled precision.
    
    Generates random elevation values rounded to specified decimal places,
    useful for testing precision detection and compression algorithms.
    
    Args:
        size: Number of pixel values to generate
        decimals: Number of decimal places to round to
        value_range: Tuple of (min_value, max_value) for elevation range
        nodata_value: Optional NoData value to include
        nodata_count: Number of NoData pixels to include
        
    Returns:
        numpy array of synthetic elevation data
        
    Example:
        >>> data = create_synthetic_elevation_data(1000, 2, (100.0, 200.0))
        >>> assert data.shape == (1000,)
        >>> assert np.all(data >= 100.0) and np.all(data <= 200.0)
    """
    # Generate random data in range
    data = np.random.uniform(value_range[0], value_range[1], size)
    
    # Round to specified decimal places
    data = np.round(data, decimals)
    
    # Add NoData values if requested
    if nodata_value is not None and nodata_count > 0:
        indices = np.random.choice(size, nodata_count, replace=False)
        data[indices] = nodata_value
    
    return data


def assert_geotiff_properties(
    ds: gdal.Dataset,
    expected_width: int,
    expected_height: int,
    expected_bands: int,
    expected_dtype: Optional[int] = None
):
    """
    Assert that a GDAL dataset has expected properties.
    
    Helper function to verify basic GeoTIFF properties in tests.
    
    Args:
        ds: GDAL Dataset to check
        expected_width: Expected raster width
        expected_height: Expected raster height
        expected_bands: Expected number of bands
        expected_dtype: Expected GDAL data type (optional)
        
    Raises:
        AssertionError: If any property doesn't match
        
    Example:
        >>> assert_geotiff_properties(ds, 256, 256, 1, gdal.GDT_Float32)
    """
    assert ds is not None, "Dataset is None"
    assert ds.RasterXSize == expected_width, f"Width mismatch: {ds.RasterXSize} != {expected_width}"
    assert ds.RasterYSize == expected_height, f"Height mismatch: {ds.RasterYSize} != {expected_height}"
    assert ds.RasterCount == expected_bands, f"Band count mismatch: {ds.RasterCount} != {expected_bands}"
    
    if expected_dtype is not None:
        band = ds.GetRasterBand(1)
        actual_dtype = band.DataType
        assert actual_dtype == expected_dtype, f"Data type mismatch: {actual_dtype} != {expected_dtype}"