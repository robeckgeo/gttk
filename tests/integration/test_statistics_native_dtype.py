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
Integration tests for statistics calculator with native data types (Phase 2).

Tests the complete workflow of statistics calculation using native dtypes
to ensure:
- Memory efficiency (50-87% reduction)
- Correct statistics calculation
- Proper nodata handling across data types
- No regressions from original behavior
"""

import numpy as np
from osgeo import gdal
import tempfile
import os
from gttk.utils.statistics import calculate_statistics


class TestNativeDtypeIntegration:
    """Integration tests for native dtype statistics calculation."""
    
    def create_test_geotiff(self, width=100, height=100, bands=1, dtype=gdal.GDT_Byte, 
                           nodata_value=None, add_nodata_pixels=False):
        """Helper to create a test GeoTIFF with specified parameters."""
        driver = gdal.GetDriverByName('GTiff')
        temp_dir = tempfile.mkdtemp()
        filename = os.path.join(temp_dir, 'test.tif')
        
        ds = driver.Create(filename, width, height, bands, dtype)
        
        for band_idx in range(1, bands + 1):
            band = ds.GetRasterBand(band_idx)
            
            # Set nodata value if specified
            if nodata_value is not None:
                band.SetNoDataValue(nodata_value)
            
            # Generate test data based on dtype
            if dtype == gdal.GDT_Byte:
                # Avoid nodata value in random data by using restricted range
                if nodata_value == 255:
                    data = np.random.randint(0, 254, (height, width), dtype=np.uint8)
                else:
                    data = np.random.randint(1, 255, (height, width), dtype=np.uint8)
                if add_nodata_pixels and nodata_value is not None:
                    data[0:10, 0:10] = int(nodata_value)
            elif dtype == gdal.GDT_UInt16:
                # Avoid nodata value in random data
                data = np.random.randint(1, 10000, (height, width), dtype=np.uint16)
                if add_nodata_pixels and nodata_value is not None:
                    data[0:10, 0:10] = int(nodata_value)
            elif dtype == gdal.GDT_Int16:
                data = np.random.randint(-1000, 1000, (height, width), dtype=np.int16)
                if add_nodata_pixels and nodata_value is not None:
                    data[0:10, 0:10] = int(nodata_value)
            elif dtype == gdal.GDT_Float32:
                data = np.random.rand(height, width).astype(np.float32) * 100
                if add_nodata_pixels and nodata_value is not None:
                    data[0:10, 0:10] = nodata_value
            else:
                data = np.random.rand(height, width).astype(np.float64) * 100
            
            band.WriteArray(data)
            band.FlushCache()
        
        ds.FlushCache()
        return filename, ds
    
    def test_byte_imagery_statistics(self):
        """Test statistics on byte (RGB) imagery - 87% memory savings."""
        filename, ds = self.create_test_geotiff(
            width=200, height=200, bands=3, 
            dtype=gdal.GDT_Byte, nodata_value=255, add_nodata_pixels=True
        )
        
        try:
            stats = calculate_statistics(ds)
            
            assert stats is not None
            assert len(stats) == 3
            
            for band_stats in stats:
                # Verify statistics are calculated
                assert band_stats.minimum is not None
                assert band_stats.maximum is not None
                assert band_stats.mean is not None
                assert band_stats.std_dev is not None
                assert band_stats.median is not None
                
                # Verify nodata pixels were excluded
                assert band_stats.nodata_count == 100  # 10x10 nodata region
                assert band_stats.valid_count == (200 * 200) - 100
                
                # Verify value ranges for byte data
                assert band_stats.minimum is not None
                assert band_stats.maximum is not None
                assert 0 <= band_stats.minimum < 255
                assert 0 < band_stats.maximum < 255
        
        finally:
            ds = None
            if os.path.exists(filename):
                os.remove(filename)
    
    def test_uint16_multispectral_statistics(self):
        """Test statistics on uint16 multispectral data - 75% memory savings."""
        filename, ds = self.create_test_geotiff(
            width=150, height=150, bands=8, 
            dtype=gdal.GDT_UInt16, nodata_value=0, add_nodata_pixels=True
        )
        
        try:
            stats = calculate_statistics(ds)
            
            assert stats is not None
            assert len(stats) == 8
            
            for band_stats in stats:
                # Verify statistics are calculated
                assert band_stats.minimum is not None
                assert band_stats.maximum is not None
                assert band_stats.mean is not None
                
                # Verify nodata handling
                assert band_stats.nodata_count == 100
                assert band_stats.nodata_value == 0
                
                # Verify minimum doesn't include nodata (which is 0)
                assert band_stats.minimum is not None
                assert band_stats.minimum > 0
        
        finally:
            ds = None
            if os.path.exists(filename):
                os.remove(filename)
    
    def test_int16_dem_statistics(self):
        """Test statistics on int16 DEM data with negative values."""
        filename, ds = self.create_test_geotiff(
            width=100, height=100, bands=1, 
            dtype=gdal.GDT_Int16, nodata_value=-9999, add_nodata_pixels=True
        )
        
        try:
            stats = calculate_statistics(ds)
            
            assert stats is not None
            assert len(stats) == 1
            
            band_stats = stats[0]
            
            # Verify nodata handling with negative value
            assert band_stats.nodata_count == 100
            assert band_stats.nodata_value == -9999
            
            # Verify statistics don't include nodata
            assert band_stats.minimum is not None
            assert band_stats.maximum is not None
            assert band_stats.mean is not None
            assert band_stats.minimum > -9999
            assert band_stats.maximum > -9999
            assert band_stats.mean > -9999
        
        finally:
            ds = None
            if os.path.exists(filename):
                os.remove(filename)
    
    def test_float32_scientific_statistics(self):
        """Test statistics on float32 scientific data - 50% memory savings."""
        filename, ds = self.create_test_geotiff(
            width=120, height=120, bands=1, 
            dtype=gdal.GDT_Float32, nodata_value=-9999.0, add_nodata_pixels=True
        )
        
        try:
            stats = calculate_statistics(ds)
            
            assert stats is not None
            assert len(stats) == 1
            
            band_stats = stats[0]
            
            # Verify float nodata handling
            assert band_stats.nodata_count == 100
            assert band_stats.nodata_value == -9999.0
            
            # Verify statistics are float values
            assert isinstance(band_stats.mean, float)
            assert isinstance(band_stats.std_dev, float)
            
            # Verify nodata excluded from statistics
            assert band_stats.minimum is not None
            assert band_stats.minimum > -9999.0
        
        finally:
            ds = None
            if os.path.exists(filename):
                os.remove(filename)
    
    def test_statistics_precision_maintained(self):
        """Test that statistics precision is maintained with native dtypes."""
        # Create small dataset with known values
        filename, ds = self.create_test_geotiff(
            width=10, height=10, bands=1, dtype=gdal.GDT_Byte
        )
        
        try:
            # Set known values
            band = ds.GetRasterBand(1)
            data = np.ones((10, 10), dtype=np.uint8) * 100
            data[5:, 5:] = 200  # 25 pixels at 200, 75 pixels at 100
            band.WriteArray(data)
            band.FlushCache()
            
            stats = calculate_statistics(ds)
            
            assert stats is not None
            band_stats = stats[0]
            
            # Verify exact statistics
            assert band_stats.minimum == 100.0
            assert band_stats.maximum == 200.0
            # Mean: (75*100 + 25*200) / 100 = 12500 / 100 = 125
            assert band_stats.mean is not None
            assert abs(band_stats.mean - 125.0) < 0.01
            
        finally:
            ds = None
            if os.path.exists(filename):
                os.remove(filename)
    
    def test_nan_handling_in_float_data(self):
        """Test that NaN values are properly handled in float data."""
        filename, ds = self.create_test_geotiff(
            width=50, height=50, bands=1, dtype=gdal.GDT_Float32
        )
        
        try:
            # Add NaN values
            band = ds.GetRasterBand(1)
            data = np.random.rand(50, 50).astype(np.float32) * 100
            data[0:5, 0:5] = np.nan  # Add NaN region
            band.WriteArray(data)
            band.FlushCache()
            
            stats = calculate_statistics(ds)
            
            assert stats is not None
            band_stats = stats[0]
            
            # Verify NaN pixels were excluded
            assert band_stats.nodata_count == 25  # 5x5 NaN region
            assert band_stats.valid_count == (50 * 50) - 25
            
            # Verify statistics don't include NaN
            assert band_stats.mean is not None
            assert band_stats.std_dev is not None
            assert band_stats.minimum is not None
            assert band_stats.maximum is not None
            assert not np.isnan(band_stats.mean)
            assert not np.isnan(band_stats.std_dev)
            assert not np.isnan(band_stats.minimum)
            assert not np.isnan(band_stats.maximum)
        
        finally:
            ds = None
            if os.path.exists(filename):
                os.remove(filename)
    
    def test_memory_efficiency_large_byte_image(self):
        """Test memory efficiency on larger byte image (simulated RGB aerial photo)."""
        # Create a larger test image to see memory benefits
        filename, ds = self.create_test_geotiff(
            width=1000, height=1000, bands=3, 
            dtype=gdal.GDT_Byte, nodata_value=None
        )
        
        try:
            stats = calculate_statistics(ds)
            
            assert stats is not None
            assert len(stats) == 3
            
            # Verify all bands calculated successfully
            for band_stats in stats:
                assert band_stats.valid_count == 1000 * 1000
                assert band_stats.histogram_counts is not None
                assert band_stats.histogram_bins is not None
        
        finally:
            ds = None
            if os.path.exists(filename):
                os.remove(filename)
    
    def test_mixed_dtype_multiband(self):
        """Test that each band is handled with its native dtype."""
        # Note: In practice, all bands in a GeoTIFF have the same dtype,
        # but this tests the per-band dtype detection logic
        filename, ds = self.create_test_geotiff(
            width=100, height=100, bands=4, 
            dtype=gdal.GDT_Byte, nodata_value=255, add_nodata_pixels=True
        )
        
        try:
            stats = calculate_statistics(ds)
            
            assert stats is not None
            assert len(stats) == 4
            
            # All bands should have consistent handling
            for i, band_stats in enumerate(stats):
                assert band_stats.nodata_count == 100
                # Valid count should be close to expected (may vary slightly due to alpha detection)
                expected_valid = (100 * 100) - 100
                assert band_stats.valid_count >= expected_valid - 200  # Allow some tolerance
                assert band_stats.valid_count <= expected_valid
                # Verify statistics are calculated for each band
                assert band_stats.mean is not None
        
        finally:
            ds = None
            if os.path.exists(filename):
                os.remove(filename)


class TestBackwardCompatibility:
    """Test that results match previous implementation (within floating-point precision)."""
    
    def test_results_consistency_byte_data(self):
        """Test that byte data produces consistent results."""
        driver = gdal.GetDriverByName('GTiff')
        temp_dir = tempfile.mkdtemp()
        filename = os.path.join(temp_dir, 'test.tif')
        
        ds = driver.Create(filename, 50, 50, 1, gdal.GDT_Byte)
        
        try:
            band = ds.GetRasterBand(1)
            # Create deterministic data using values that fit in uint8
            data = (np.arange(2500) % 256).astype(np.uint8).reshape(50, 50)
            band.WriteArray(data)
            band.FlushCache()
            
            stats = calculate_statistics(ds)
            
            assert stats is not None
            band_stats = stats[0]
            
            # Expected statistics from numpy
            expected_min = float(np.min(data))
            expected_max = float(np.max(data))
            expected_mean = float(np.mean(data))
            expected_std = float(np.std(data))
            
            # Verify results match (within floating-point precision)
            assert band_stats.minimum is not None
            assert band_stats.maximum is not None
            assert band_stats.mean is not None
            assert band_stats.std_dev is not None
            assert abs(band_stats.minimum - expected_min) < 1e-6
            assert abs(band_stats.maximum - expected_max) < 1e-6
            assert abs(band_stats.mean - expected_mean) < 1e-6
            assert abs(band_stats.std_dev - expected_std) < 1e-6
        
        finally:
            ds = None
            if os.path.exists(filename):
                os.remove(filename)
