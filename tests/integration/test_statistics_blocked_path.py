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
Integration tests for block-based statistics calculation.

Tests that the blocked statistics path produces correct results and matches
the fast path for files that can be processed both ways.
"""

import pytest
import numpy as np
from osgeo import gdal
from gttk.utils.statistics import (
    calculate_statistics,
    _calculate_statistics_blocked
)


class TestBlockedStatisticsPath:
    """Integration tests for block-based statistics calculation."""
    
    def test_blocked_matches_fast_path_simple(self, tmp_path):
        """Verify blocked path produces same results as fast path for simple file."""
        # Create a test file small enough for both paths
        width, height = 512, 512
        driver = gdal.GetDriverByName('GTiff')
        filepath = str(tmp_path / "test_simple.tif")
        
        dataset = driver.Create(filepath, width, height, 1, gdal.GDT_Float32)
        band = dataset.GetRasterBand(1)
        
        # Create data with known statistics
        np.random.seed(42)
        data = np.random.normal(100.0, 15.0, (height, width)).astype(np.float32)
        band.WriteArray(data)
        band.FlushCache()
        
        # Calculate with fast path (default)
        fast_stats = calculate_statistics(dataset)
        
        # Calculate with blocked path
        blocked_stats = _calculate_statistics_blocked(dataset, block_size=(128, 128))
        
        assert fast_stats is not None
        assert blocked_stats is not None
        assert len(fast_stats) == len(blocked_stats) == 1
        
        # Compare statistics (within reasonable tolerance)
        fast = fast_stats[0]
        blocked = blocked_stats[0]
        
        assert fast.valid_count == blocked.valid_count
        assert fast.minimum is not None and blocked.minimum is not None
        assert np.isclose(fast.minimum, blocked.minimum, rtol=1e-6)
        assert fast.maximum is not None and blocked.maximum is not None
        assert np.isclose(fast.maximum, blocked.maximum, rtol=1e-6)
        assert fast.mean is not None and blocked.mean is not None
        assert np.isclose(fast.mean, blocked.mean, rtol=1e-6)
        assert fast.std_dev is not None and blocked.std_dev is not None
        assert np.isclose(fast.std_dev, blocked.std_dev, rtol=1e-6)

        dataset = None
    
    def test_blocked_with_nodata(self, tmp_path):
        """Test blocked path with NoData values."""
        width, height = 256, 256
        driver = gdal.GetDriverByName('GTiff')
        filepath = str(tmp_path / "test_nodata.tif")
        
        dataset = driver.Create(filepath, width, height, 1, gdal.GDT_UInt16)
        band = dataset.GetRasterBand(1)
        
        # Set NoData value
        nodata_value = 0
        band.SetNoDataValue(nodata_value)
        
        # Create data with some NoData pixels
        data = np.random.randint(1, 1000, (height, width), dtype=np.uint16)
        # Set some pixels to NoData
        data[0:50, 0:50] = nodata_value
        band.WriteArray(data)
        band.FlushCache()
        
        # Calculate with blocked path
        stats = _calculate_statistics_blocked(dataset, block_size=(64, 64))
        
        assert stats is not None
        assert len(stats) == 1
        
        # Verify NoData pixels were excluded
        expected_nodata_count = 50 * 50
        assert stats[0].nodata_count == expected_nodata_count
        assert stats[0].valid_count == (width * height - expected_nodata_count)
        
        # Verify statistics don't include NoData value
        assert stats[0].minimum is not None
        assert stats[0].minimum > nodata_value
        
        dataset = None
    
    def test_blocked_with_rgba(self, tmp_path):
        """Test blocked path with RGBA data (alpha channel handling)."""
        width, height = 200, 200
        driver = gdal.GetDriverByName('GTiff')
        filepath = str(tmp_path / "test_rgba.tif")
        
        dataset = driver.Create(filepath, width, height, 4, gdal.GDT_Byte,
                               options=['PHOTOMETRIC=RGB'])
        
        # Set color interpretation
        dataset.GetRasterBand(1).SetColorInterpretation(gdal.GCI_RedBand)
        dataset.GetRasterBand(2).SetColorInterpretation(gdal.GCI_GreenBand)
        dataset.GetRasterBand(3).SetColorInterpretation(gdal.GCI_BlueBand)
        dataset.GetRasterBand(4).SetColorInterpretation(gdal.GCI_AlphaBand)
        
        # Fill bands
        for i in range(1, 4):  # RGB
            band = dataset.GetRasterBand(i)
            data = np.random.randint(0, 256, (height, width), dtype=np.uint8)
            band.WriteArray(data)
        
        # Alpha band with some transparent pixels
        alpha_band = dataset.GetRasterBand(4)
        alpha_data = np.full((height, width), 255, dtype=np.uint8)
        alpha_data[0:20, 0:20] = 0  # Transparent region
        alpha_band.WriteArray(alpha_data)
        dataset.FlushCache()
        
        # Calculate with blocked path
        stats = _calculate_statistics_blocked(dataset, block_size=(50, 50))
        
        assert stats is not None
        assert len(stats) == 4
        
        # Verify alpha=0 count is reported
        expected_alpha_0 = 20 * 20
        for band_stats in stats:
            assert band_stats.alpha_0_count == expected_alpha_0
        
        # RGB bands should exclude alpha=0 pixels from valid count
        for i in range(3):
            expected_valid = width * height - expected_alpha_0
            assert stats[i].valid_count == expected_valid
        
        # Alpha band should include alpha=0 in its histogram
        alpha_stats = stats[3]
        assert alpha_stats.band_name == 'Alpha'
        # Alpha band's valid count may differ as it doesn't exclude itself
        
        dataset = None
    
    def test_blocked_with_multiple_dtypes(self, tmp_path):
        """Test blocked path with different data types."""
        test_cases = [
            (gdal.GDT_Byte, np.uint8, 0, 255),
            (gdal.GDT_UInt16, np.uint16, 0, 65535),
            (gdal.GDT_Int16, np.int16, -1000, 1000),
            (gdal.GDT_Float32, np.float32, -100.5, 100.5),
        ]
        
        for gdal_type, np_dtype, min_val, max_val in test_cases:
            width, height = 128, 128
            driver = gdal.GetDriverByName('GTiff')
            filepath = str(tmp_path / f"test_{gdal.GetDataTypeName(gdal_type)}.tif")
            
            dataset = driver.Create(filepath, width, height, 1, gdal_type)
            band = dataset.GetRasterBand(1)
            
            # Create appropriate data for type
            if np.issubdtype(np_dtype, np.integer):
                data = np.random.randint(min_val, max_val + 1, (height, width), dtype=np_dtype)
            else:
                data = np.random.uniform(min_val, max_val, (height, width)).astype(np_dtype)
            
            band.WriteArray(data)
            band.FlushCache()
            
            # Calculate with blocked path
            stats = _calculate_statistics_blocked(dataset, block_size=(32, 32))
            
            assert stats is not None, f"Failed for {gdal.GetDataTypeName(gdal_type)}"
            assert len(stats) == 1
            assert stats[0].valid_count == width * height
            
            # Verify min/max are within expected range
            assert stats[0].minimum >= min_val
            assert stats[0].maximum <= max_val
            
            dataset = None
    
    def test_blocked_empty_file(self, tmp_path):
        """Test blocked path with file containing all NoData."""
        width, height = 100, 100
        driver = gdal.GetDriverByName('GTiff')
        filepath = str(tmp_path / "test_empty.tif")
        
        dataset = driver.Create(filepath, width, height, 1, gdal.GDT_Float32)
        band = dataset.GetRasterBand(1)
        
        # Set NoData and fill entire image with NoData
        nodata_value = -9999.0
        band.SetNoDataValue(nodata_value)
        data = np.full((height, width), nodata_value, dtype=np.float32)
        band.WriteArray(data)
        band.FlushCache()
        
        # Calculate with blocked path
        stats = _calculate_statistics_blocked(dataset, block_size=(50, 50))
        
        assert stats is not None
        assert len(stats) == 1
        
        # Verify all pixels marked as NoData
        assert stats[0].nodata_count == width * height
        assert stats[0].valid_count == 0
        
        # Statistics should be None
        assert stats[0].minimum is None
        assert stats[0].maximum is None
        assert stats[0].mean is None
        assert stats[0].std_dev is None
        
        dataset = None
    
    def test_blocked_single_block(self, tmp_path):
        """Test blocked path with file smaller than block size."""
        width, height = 100, 100
        driver = gdal.GetDriverByName('GTiff')
        filepath = str(tmp_path / "test_single_block.tif")
        
        dataset = driver.Create(filepath, width, height, 1, gdal.GDT_Byte)
        band = dataset.GetRasterBand(1)
        
        data = np.random.randint(0, 256, (height, width), dtype=np.uint8)
        band.WriteArray(data)
        band.FlushCache()
        
        # Use block size larger than image
        stats = _calculate_statistics_blocked(dataset, block_size=(256, 256))
        
        assert stats is not None
        assert len(stats) == 1
        assert stats[0].valid_count == width * height
        
        dataset = None
    
    def test_blocked_multiband(self, tmp_path):
        """Test blocked path with multi-band file."""
        width, height = 150, 150
        num_bands = 8
        driver = gdal.GetDriverByName('GTiff')
        filepath = str(tmp_path / "test_multiband.tif")
        
        dataset = driver.Create(filepath, width, height, num_bands, gdal.GDT_UInt16)
        
        for i in range(1, num_bands + 1):
            band = dataset.GetRasterBand(i)
            # Each band has different value range
            data = np.random.randint(i * 100, i * 100 + 500, (height, width), dtype=np.uint16)
            band.WriteArray(data)
        
        dataset.FlushCache()
        
        # Calculate with blocked path
        stats = _calculate_statistics_blocked(dataset, block_size=(50, 50))
        
        assert stats is not None
        assert len(stats) == num_bands
        
        # Verify each band has statistics
        for i, band_stats in enumerate(stats):
            assert band_stats.valid_count == width * height
            assert band_stats.minimum is not None
            assert band_stats.minimum >= i * 100
            assert band_stats.maximum is not None
            assert band_stats.maximum < (i + 1) * 100 + 500
        
        dataset = None
    
    def test_blocked_histogram_generation(self, tmp_path):
        """Test that blocked path generates proper histograms."""
        width, height = 200, 200
        driver = gdal.GetDriverByName('GTiff')
        filepath = str(tmp_path / "test_histogram.tif")
        
        dataset = driver.Create(filepath, width, height, 1, gdal.GDT_Byte)
        band = dataset.GetRasterBand(1)
        
        # Create data with known distribution
        data = np.tile(np.arange(256, dtype=np.uint8), (height * width // 256 + 1))
        data = data[:height * width].reshape(height, width)
        band.WriteArray(data)
        band.FlushCache()
        
        # Calculate with blocked path
        stats = _calculate_statistics_blocked(dataset, block_size=(64, 64))
        
        assert stats is not None
        assert len(stats) == 1
        
        # Verify histogram was generated
        assert stats[0].histogram_counts is not None
        assert stats[0].histogram_bins is not None
        assert len(stats[0].histogram_counts) > 0
        
        # For byte data, we should have close to uniform distribution
        total_counts = sum(stats[0].histogram_counts)
        assert total_counts == width * height
        
        dataset = None


class TestBlockedVsFastPath:
    """Compare blocked and fast paths to ensure consistency."""
    
    def test_statistical_equivalence(self, tmp_path):
        """Ensure blocked and fast paths produce equivalent statistics."""
        width, height = 400, 400
        driver = gdal.GetDriverByName('GTiff')
        filepath = str(tmp_path / "test_equivalence.tif")
        
        dataset = driver.Create(filepath, width, height, 3, gdal.GDT_Float32)
        
        # Create bands with different distributions
        np.random.seed(123)
        for i in range(1, 4):
            band = dataset.GetRasterBand(i)
            data = np.random.normal(i * 50.0, i * 10.0, (height, width)).astype(np.float32)
            band.WriteArray(data)
        
        dataset.FlushCache()
        
        # Calculate with both paths
        fast_stats = calculate_statistics(dataset)
        blocked_stats = _calculate_statistics_blocked(dataset, block_size=(100, 100))
        
        assert fast_stats is not None
        assert blocked_stats is not None
        assert len(fast_stats) == len(blocked_stats) == 3
        
        # Compare each band
        for i in range(3):
            fast = fast_stats[i]
            blocked = blocked_stats[i]
            
            # Counts should match exactly
            assert fast.valid_count == blocked.valid_count
            
            # Statistics should match within floating-point precision
            assert fast.minimum is not None and blocked.minimum is not None
            assert np.isclose(fast.minimum, blocked.minimum, rtol=1e-6), \
                f"Band {i+1} minimum mismatch"
            assert fast.maximum is not None and blocked.maximum is not None
            assert np.isclose(fast.maximum, blocked.maximum, rtol=1e-6), \
                f"Band {i+1} maximum mismatch"
            assert fast.mean is not None and blocked.mean is not None
            assert np.isclose(fast.mean, blocked.mean, rtol=1e-6), \
                f"Band {i+1} mean mismatch"
            assert fast.std_dev is not None and blocked.std_dev is not None
            assert np.isclose(fast.std_dev, blocked.std_dev, rtol=1e-6), \
                f"Band {i+1} std_dev mismatch"
        
        dataset = None


if __name__ == "__main__":
    pytest.main([__file__, "-v"])
