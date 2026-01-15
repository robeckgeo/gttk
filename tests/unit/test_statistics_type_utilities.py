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
Unit tests for statistics calculator type utilities (Phase 1).

Tests native data type support functionality including:
- GDAL to NumPy dtype mapping
- Optimal dtype selection
- Safe NoData comparison for different types
- Data promotion for statistics
"""

import numpy as np
from osgeo import gdal
from unittest.mock import Mock
from gttk.utils.statistics import (
    GDAL_TO_NUMPY_DTYPE,
    _get_optimal_dtype,
    _safe_nodata_comparison,
    _promote_for_statistics
)


class TestGDALToNumpyDtypeMapping:
    """Test GDAL_TO_NUMPY_DTYPE mapping dictionary."""
    
    def test_mapping_contains_all_common_types(self):
        """Verify all common GDAL types are mapped."""
        expected_types = [
            gdal.GDT_Byte,
            gdal.GDT_Int16,
            gdal.GDT_UInt16,
            gdal.GDT_Int32,
            gdal.GDT_UInt32,
            gdal.GDT_Float32,
            gdal.GDT_Float64,
        ]
        
        for gdal_type in expected_types:
            assert gdal_type in GDAL_TO_NUMPY_DTYPE, \
                f"GDAL type {gdal.GetDataTypeName(gdal_type)} not in mapping"
    
    def test_byte_maps_to_uint8(self):
        """Test Byte data maps to uint8 (87.5% memory savings)."""
        assert GDAL_TO_NUMPY_DTYPE[gdal.GDT_Byte] == np.uint8
    
    def test_uint16_maps_to_uint16(self):
        """Test UInt16 maps to uint16 (75% memory savings)."""
        assert GDAL_TO_NUMPY_DTYPE[gdal.GDT_UInt16] == np.uint16
    
    def test_int16_maps_to_int16(self):
        """Test Int16 maps to int16."""
        assert GDAL_TO_NUMPY_DTYPE[gdal.GDT_Int16] == np.int16
    
    def test_float32_maps_to_float32(self):
        """Test Float32 maps to float32 (50% memory savings)."""
        assert GDAL_TO_NUMPY_DTYPE[gdal.GDT_Float32] == np.float32
    
    def test_float64_maps_to_float64(self):
        """Test Float64 maps to float64 (no conversion)."""
        assert GDAL_TO_NUMPY_DTYPE[gdal.GDT_Float64] == np.float64


class TestGetOptimalDtype:
    """Test _get_optimal_dtype() function."""
    
    def test_byte_band_returns_uint8(self):
        """Test byte band returns uint8."""
        mock_band = Mock(spec=gdal.Band)
        mock_band.DataType = gdal.GDT_Byte
        
        result = _get_optimal_dtype(mock_band)
        assert result == np.uint8
    
    def test_uint16_band_returns_uint16(self):
        """Test uint16 band returns uint16."""
        mock_band = Mock(spec=gdal.Band)
        mock_band.DataType = gdal.GDT_UInt16
        
        result = _get_optimal_dtype(mock_band)
        assert result == np.uint16
    
    def test_int16_band_returns_int16(self):
        """Test int16 band returns int16."""
        mock_band = Mock(spec=gdal.Band)
        mock_band.DataType = gdal.GDT_Int16
        
        result = _get_optimal_dtype(mock_band)
        assert result == np.int16
    
    def test_float32_band_returns_float32(self):
        """Test float32 band returns float32."""
        mock_band = Mock(spec=gdal.Band)
        mock_band.DataType = gdal.GDT_Float32
        
        result = _get_optimal_dtype(mock_band)
        assert result == np.float32
    
    def test_float64_band_returns_float64(self):
        """Test float64 band returns float64."""
        mock_band = Mock(spec=gdal.Band)
        mock_band.DataType = gdal.GDT_Float64
        
        result = _get_optimal_dtype(mock_band)
        assert result == np.float64
    
    def test_unknown_type_returns_float64_fallback(self):
        """Test unknown GDAL type falls back to float64."""
        mock_band = Mock(spec=gdal.Band)
        mock_band.DataType = 999  # Invalid/unknown type
        
        result = _get_optimal_dtype(mock_band)
        assert result == np.float64


class TestSafeNodataComparisonInteger:
    """Test _safe_nodata_comparison() for integer types."""
    
    def test_int16_exact_match(self):
        """Test integer nodata comparison with exact match."""
        data = np.array([100, -9999, 200, -9999, 300], dtype=np.int16)
        nodata_value = -9999
        
        mask = _safe_nodata_comparison(data, nodata_value, np.dtype(np.int16))
        
        expected = np.array([False, True, False, True, False])
        np.testing.assert_array_equal(mask, expected)
    
    def test_uint8_exact_match(self):
        """Test uint8 nodata comparison."""
        data = np.array([0, 50, 255, 100, 255], dtype=np.uint8)
        nodata_value = 255
        
        mask = _safe_nodata_comparison(data, nodata_value, np.dtype(np.uint8))
        
        expected = np.array([False, False, True, False, True])
        np.testing.assert_array_equal(mask, expected)
    
    def test_int32_with_nan_pixels(self):
        """Test integer type also detects NaN pixels."""
        # Note: Integer arrays can't naturally hold NaN, but if they're
        # cast from float, we handle it
        data = np.array([100, 200, 300], dtype=np.int32)
        nodata_value = -9999
        
        mask = _safe_nodata_comparison(data, nodata_value, np.dtype(np.int32))
        
        # Should find no matches since no -9999 or NaN
        expected = np.array([False, False, False])
        np.testing.assert_array_equal(mask, expected)
    
    def test_integer_no_nodata_value(self):
        """Test integer data with no nodata value."""
        data = np.array([100, 200, 300], dtype=np.int16)
        nodata_value = None
        
        mask = _safe_nodata_comparison(data, nodata_value, np.dtype(np.int16))
        
        # Should return all False for integer type with no nodata
        expected = np.array([False, False, False])
        np.testing.assert_array_equal(mask, expected)


class TestSafeNodataComparisonFloat:
    """Test _safe_nodata_comparison() for float types."""
    
    def test_float32_exact_match(self):
        """Test float32 nodata comparison with tolerance."""
        data = np.array([100.0, -9999.0, 200.0, -9999.0, 300.0], dtype=np.float32)
        nodata_value = -9999.0
        
        mask = _safe_nodata_comparison(data, nodata_value, np.dtype(np.float32))
        
        expected = np.array([False, True, False, True, False])
        np.testing.assert_array_equal(mask, expected)
    
    def test_float64_exact_match(self):
        """Test float64 nodata comparison."""
        data = np.array([100.0, -9999.0, 200.0], dtype=np.float64)
        nodata_value = -9999.0
        
        mask = _safe_nodata_comparison(data, nodata_value, np.dtype(np.float64))
        
        expected = np.array([False, True, False])
        np.testing.assert_array_equal(mask, expected)
    
    def test_float_with_nan_nodata(self):
        """Test float data with NaN as nodata value."""
        data = np.array([100.0, np.nan, 200.0, np.nan, 300.0], dtype=np.float32)
        nodata_value = np.nan
        
        mask = _safe_nodata_comparison(data, nodata_value, np.dtype(np.float32))
        
        expected = np.array([False, True, False, True, False])
        np.testing.assert_array_equal(mask, expected)
    
    def test_float_detects_nan_pixels_with_numeric_nodata(self):
        """Test float comparison also finds NaN pixels when nodata is numeric."""
        data = np.array([100.0, -9999.0, np.nan, 200.0], dtype=np.float32)
        nodata_value = -9999.0
        
        mask = _safe_nodata_comparison(data, nodata_value, np.dtype(np.float32))
        
        expected = np.array([False, True, True, False])
        np.testing.assert_array_equal(mask, expected)
    
    def test_float_no_nodata_finds_nan(self):
        """Test float data with no nodata value still finds NaN."""
        data = np.array([100.0, np.nan, 200.0, 300.0], dtype=np.float32)
        nodata_value = None
        
        mask = _safe_nodata_comparison(data, nodata_value, np.dtype(np.float32))
        
        expected = np.array([False, True, False, False])
        np.testing.assert_array_equal(mask, expected)
    
    def test_float_tolerance_comparison(self):
        """Test float comparison uses tolerance for near-equal values."""
        # Create values that are very close to nodata (within float32 precision)
        data = np.array([100.0, -9999.0, -9999.0000001, 200.0], dtype=np.float32)
        nodata_value = -9999.0
        
        mask = _safe_nodata_comparison(data, nodata_value, np.dtype(np.float32))
        
        # Both -9999.0 and -9999.0000001 should match due to tolerance
        assert mask[1] == True  # Exact match
        assert mask[2] == True  # Within tolerance


class TestPromoteForStatistics:
    """Test _promote_for_statistics() function."""
    
    def test_uint8_promotes_to_float64(self):
        """Test uint8 data promotes to float64."""
        data = np.array([100, 150, 200], dtype=np.uint8)
        
        result = _promote_for_statistics(data)
        
        assert result.dtype == np.float64
        np.testing.assert_array_equal(result, [100.0, 150.0, 200.0])
    
    def test_uint16_promotes_to_float64(self):
        """Test uint16 data promotes to float64."""
        data = np.array([1000, 2000, 3000], dtype=np.uint16)
        
        result = _promote_for_statistics(data)
        
        assert result.dtype == np.float64
        np.testing.assert_array_equal(result, [1000.0, 2000.0, 3000.0])
    
    def test_int16_promotes_to_float64(self):
        """Test int16 data promotes to float64."""
        data = np.array([-1000, 0, 1000], dtype=np.int16)
        
        result = _promote_for_statistics(data)
        
        assert result.dtype == np.float64
        np.testing.assert_array_equal(result, [-1000.0, 0.0, 1000.0])
    
    def test_float32_promotes_to_float64(self):
        """Test float32 data promotes to float64."""
        data = np.array([1.5, 2.5, 3.5], dtype=np.float32)
        
        result = _promote_for_statistics(data)
        
        assert result.dtype == np.float64
        # Use approximate comparison for float conversion
        np.testing.assert_allclose(result, [1.5, 2.5, 3.5])
    
    def test_float64_returns_unchanged(self):
        """Test float64 data returns unchanged (no conversion)."""
        data = np.array([1.5, 2.5, 3.5], dtype=np.float64)
        
        result = _promote_for_statistics(data)
        
        assert result.dtype == np.float64
        assert result is data  # Should be same object, not a copy
    
    def test_promotion_preserves_values(self):
        """Test promotion preserves all values accurately."""
        # Test with edge values for uint8
        data = np.array([0, 127, 255], dtype=np.uint8)
        
        result = _promote_for_statistics(data)
        
        np.testing.assert_array_equal(result, [0.0, 127.0, 255.0])
    
    def test_large_uint16_values_preserved(self):
        """Test large uint16 values are preserved in float64."""
        data = np.array([0, 32768, 65535], dtype=np.uint16)
        
        result = _promote_for_statistics(data)
        
        # Float64 has enough precision for all uint16 values
        np.testing.assert_array_equal(result, [0.0, 32768.0, 65535.0])


class TestTypeUtilitiesIntegration:
    """Integration tests for type utilities working together."""
    
    def test_workflow_byte_data(self):
        """Test complete workflow: optimal dtype → masking → promotion."""
        # Simulate byte band workflow
        mock_band = Mock(spec=gdal.Band)
        mock_band.DataType = gdal.GDT_Byte
        
        # Step 1: Get optimal dtype
        dtype = _get_optimal_dtype(mock_band)
        assert dtype == np.uint8
        
        # Step 2: Create data with nodata
        data = np.array([0, 100, 255, 150, 255], dtype=dtype)
        nodata_value = 255
        
        # Step 3: Create mask
        mask = _safe_nodata_comparison(data, nodata_value, dtype)
        valid_data = data[~mask]
        
        # Step 4: Promote for statistics
        promoted = _promote_for_statistics(valid_data)
        
        assert promoted.dtype == np.float64
        np.testing.assert_array_equal(promoted, [0.0, 100.0, 150.0])
    
    def test_workflow_uint16_data(self):
        """Test complete workflow with uint16 multispectral data."""
        mock_band = Mock(spec=gdal.Band)
        mock_band.DataType = gdal.GDT_UInt16
        
        dtype = _get_optimal_dtype(mock_band)
        assert dtype == np.uint16
        
        data = np.array([0, 5000, 10000, 0, 15000], dtype=dtype)
        nodata_value = 0
        
        mask = _safe_nodata_comparison(data, nodata_value, dtype)
        valid_data = data[~mask]
        
        promoted = _promote_for_statistics(valid_data)
        
        assert promoted.dtype == np.float64
        np.testing.assert_array_equal(promoted, [5000.0, 10000.0, 15000.0])
    
    def test_workflow_float32_scientific_data(self):
        """Test complete workflow with float32 scientific data."""
        mock_band = Mock(spec=gdal.Band)
        mock_band.DataType = gdal.GDT_Float32
        
        dtype = _get_optimal_dtype(mock_band)
        assert dtype == np.float32
        
        data = np.array([-9999.0, 1.5, 2.5, np.nan, 3.5], dtype=dtype)
        nodata_value = -9999.0
        
        mask = _safe_nodata_comparison(data, nodata_value, dtype)
        valid_data = data[~mask]
        
        promoted = _promote_for_statistics(valid_data)
        
        assert promoted.dtype == np.float64
        np.testing.assert_allclose(promoted, [1.5, 2.5, 3.5])
