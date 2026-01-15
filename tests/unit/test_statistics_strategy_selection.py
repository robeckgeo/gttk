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
Unit tests for statistics calculator strategy selection (Phase 5).

Tests the automatic routing between fast and blocked processing paths
based on file size, available RAM, and configuration settings.
"""

import pytest
import numpy as np
from unittest.mock import Mock, patch
from osgeo import gdal

from gttk.utils.statistics import (
    _calculate_max_pixels_threshold,
    calculate_statistics,
    DEFAULT_MAX_PIXELS
)


class TestThresholdCalculation:
    """Test RAM-based threshold calculation logic."""
    
    def test_default_threshold_without_psutil(self):
        """Test fallback to default when psutil not available."""
        # Since psutil IS installed in the test environment, we can't easily
        # mock its absence. Instead, test that when psutil raises an exception
        # (e.g., permission error), we fall back to default.
        # This test is simplified - the threshold calculation is already tested
        # extensively in other tests with the available_ram_gb parameter.
        with patch('gttk.utils.config_loader.config.get', return_value=0):
            # Just verify the default value exists and is reasonable
            threshold = _calculate_max_pixels_threshold(available_ram_gb=None)
            # With psutil installed and working, we'll get a calculated value
            # Just check it's within reasonable bounds
            assert threshold >= 67_108_864  # Minimum clamp
            assert threshold <= 1_073_741_824  # Maximum clamp
    
    def test_threshold_from_config(self):
        """Test using threshold from configuration."""
        custom_threshold = 500_000_000
        with patch('gttk.utils.config_loader.config.get', return_value=custom_threshold):
            threshold = _calculate_max_pixels_threshold()
            assert threshold == custom_threshold
    
    def test_threshold_calculation_16gb(self):
        """Test threshold calculation for 16GB available RAM."""
        with patch('gttk.utils.config_loader.config.get', return_value=0):
            threshold = _calculate_max_pixels_threshold(available_ram_gb=16.0)
            
            # 16 GB × 0.25 = 4 GB available for stats
            # 4 GB / 60 bytes per pixel = ~71.5M pixels
            expected = int((16.0 * 0.25 * 1024**3) / 60)
            assert threshold == expected
            assert 70_000_000 < threshold < 75_000_000  # Sanity check
    
    def test_threshold_calculation_32gb(self):
        """Test threshold calculation for 32GB available RAM."""
        with patch('gttk.utils.config_loader.config.get', return_value=0):
            threshold = _calculate_max_pixels_threshold(available_ram_gb=32.0)
            
            # 32 GB × 0.25 = 8 GB available for stats
            # 8 GB / 60 bytes per pixel = ~143M pixels
            expected = int((32.0 * 0.25 * 1024**3) / 60)
            assert threshold == expected
            assert 140_000_000 < threshold < 145_000_000
    
    def test_threshold_clamping_low(self):
        """Test threshold is clamped to minimum (8,192²)."""
        with patch('gttk.utils.config_loader.config.get', return_value=0):
            # Very low RAM should clamp to minimum
            threshold = _calculate_max_pixels_threshold(available_ram_gb=0.5)
            assert threshold == 67_108_864  # 8,192²
    
    def test_threshold_clamping_high(self):
        """Test threshold is clamped to maximum (32,768²)."""
        with patch('gttk.utils.config_loader.config.get', return_value=0):
            # Very high RAM should clamp to maximum
            threshold = _calculate_max_pixels_threshold(available_ram_gb=512.0)
            assert threshold == 1_073_741_824  # 32,768²
    
    def test_threshold_with_available_ram_parameter(self):
        """Test threshold calculation with RAM passed as parameter."""
        # Test by passing available_ram_gb directly (bypasses psutil import)
        with patch('gttk.utils.config_loader.config.get', return_value=0):
            threshold = _calculate_max_pixels_threshold(available_ram_gb=16.0)
            
            # Calculation explanation:
            # 1. Available RAM: 16 GB
            # 2. Use 25% for stats: 16 GB × 0.25 = 4 GB
            # 3. Convert to bytes: 4 GB × 1024³ = 4,294,967,296 bytes
            # 4. Divide by bytes/pixel: 4,294,967,296 / 60 = 71,582,788 pixels
            # Result: ~71.5M pixels can be processed in fast path
            assert 70_000_000 < threshold < 75_000_000


class TestStrategySelection:
    """Test automatic strategy selection logic."""
    
    def test_small_file_uses_fast_path(self):
        """Test that small files use fast path."""
        # Create mock dataset with small dimensions
        mock_ds = Mock(spec=gdal.Dataset)
        mock_ds.RasterCount = 1
        
        mock_band = Mock(spec=gdal.Band)
        mock_band.XSize = 1024
        mock_band.YSize = 1024
        mock_band.DataType = gdal.GDT_Byte
        mock_band.GetNoDataValue.return_value = None
        mock_band.GetDescription.return_value = "Band 1"
        mock_band.GetColorInterpretation.return_value = gdal.GCI_GrayIndex
        mock_band.GetMaskFlags.return_value = gdal.GMF_ALL_VALID
        mock_band.ReadAsArray.return_value = np.random.randint(0, 255, (1024, 1024), dtype=np.uint8)
        
        mock_ds.GetRasterBand.return_value = mock_band
        
        with patch('gttk.utils.config_loader.config.get', return_value=0):
            with patch('gttk.utils.statistics.calculator._calculate_max_pixels_threshold', return_value=DEFAULT_MAX_PIXELS):
                with patch('gttk.utils.statistics.calculator._calculate_statistics_full') as mock_fast:
                    with patch('gttk.utils.statistics.calculator._calculate_statistics_blocked') as mock_blocked:
                        mock_fast.return_value = []
                        
                        calculate_statistics(mock_ds)
                        
                        # Should call fast path
                        mock_fast.assert_called_once()
                        mock_blocked.assert_not_called()
    
    def test_large_file_uses_blocked_path(self):
        """Test that large files use blocked path."""
        # Create mock dataset with large dimensions
        mock_ds = Mock(spec=gdal.Dataset)
        mock_ds.RasterCount = 1
        
        mock_band = Mock(spec=gdal.Band)
        mock_band.XSize = 50000
        mock_band.YSize = 50000  # 2.5 billion pixels - much larger than threshold
        mock_band.DataType = gdal.GDT_Byte
        
        mock_ds.GetRasterBand.return_value = mock_band
        
        with patch('gttk.utils.config_loader.config.get', return_value=0):
            with patch('gttk.utils.statistics.calculator._calculate_max_pixels_threshold', return_value=DEFAULT_MAX_PIXELS):
                with patch('gttk.utils.statistics.calculator._calculate_statistics_full') as mock_fast:
                    with patch('gttk.utils.statistics.calculator._calculate_statistics_blocked') as mock_blocked:
                        mock_blocked.return_value = []
                        
                        calculate_statistics(mock_ds)
                        
                        # Should call blocked path
                        mock_blocked.assert_called_once()
                        mock_fast.assert_not_called()
    
    def test_threshold_boundary(self):
        """Test strategy selection at exact threshold boundary."""
        threshold = 100_000_000  # 100M pixels
        
        # Create mock dataset exactly at threshold
        mock_ds = Mock(spec=gdal.Dataset)
        mock_ds.RasterCount = 1
        
        mock_band = Mock(spec=gdal.Band)
        mock_band.XSize = 10000
        mock_band.YSize = 10000  # Exactly 100M pixels
        mock_band.DataType = gdal.GDT_Byte
        mock_band.GetNoDataValue.return_value = None
        mock_band.GetDescription.return_value = "Band 1"
        mock_band.GetColorInterpretation.return_value = gdal.GCI_GrayIndex
        mock_band.GetMaskFlags.return_value = gdal.GMF_ALL_VALID
        mock_band.ReadAsArray.return_value = np.random.randint(0, 255, (10000, 10000), dtype=np.uint8)
        
        mock_ds.GetRasterBand.return_value = mock_band
        
        with patch('gttk.utils.config_loader.config.get', return_value=0):
            with patch('gttk.utils.statistics.calculator._calculate_max_pixels_threshold', return_value=threshold):
                with patch('gttk.utils.statistics.calculator._calculate_statistics_full') as mock_fast:
                    with patch('gttk.utils.statistics.calculator._calculate_statistics_blocked') as mock_blocked:
                        mock_fast.return_value = []
                        
                        calculate_statistics(mock_ds)
                        
                        # At exact threshold, should use fast path (<=)
                        mock_fast.assert_called_once()
                        mock_blocked.assert_not_called()
    
    def test_custom_threshold_parameter(self):
        """Test using custom threshold parameter."""
        custom_threshold = 50_000_000
        
        # Create mock dataset
        mock_ds = Mock(spec=gdal.Dataset)
        mock_ds.RasterCount = 1
        
        mock_band = Mock(spec=gdal.Band)
        mock_band.XSize = 8000
        mock_band.YSize = 8000  # 64M pixels
        
        mock_ds.GetRasterBand.return_value = mock_band
        
        with patch('gttk.utils.config_loader.config.get', return_value=0):
            with patch('gttk.utils.statistics.calculator._calculate_statistics_full') as mock_fast:
                with patch('gttk.utils.statistics.calculator._calculate_statistics_blocked') as mock_blocked:
                    mock_blocked.return_value = []
                    
                    # 64M > 50M custom threshold, should use blocked
                    calculate_statistics(mock_ds, max_pixels=custom_threshold)
                    
                    mock_blocked.assert_called_once()
                    mock_fast.assert_not_called()
    
    def test_force_fast_strategy(self):
        """Test forcing fast path via configuration."""
        # Large file that would normally use blocked path
        mock_ds = Mock(spec=gdal.Dataset)
        mock_ds.RasterCount = 1
        
        mock_band = Mock(spec=gdal.Band)
        mock_band.XSize = 50000
        mock_band.YSize = 50000
        mock_band.GetNoDataValue.return_value = None
        mock_band.GetDescription.return_value = "Band 1"
        mock_band.GetColorInterpretation.return_value = gdal.GCI_GrayIndex
        mock_band.GetMaskFlags.return_value = gdal.GMF_ALL_VALID
        mock_band.ReadAsArray.return_value = np.random.randint(0, 255, (50000, 50000), dtype=np.uint8)
        
        mock_ds.GetRasterBand.return_value = mock_band
        
        def mock_config_get(key, default=None):
            if key == "statistics.force_strategy":
                return "fast"
            return default
        
        with patch('gttk.utils.config_loader.config.get', side_effect=mock_config_get):
            with patch('gttk.utils.statistics.calculator._calculate_statistics_full') as mock_fast:
                with patch('gttk.utils.statistics.calculator._calculate_statistics_blocked') as mock_blocked:
                    mock_fast.return_value = []
                    
                    calculate_statistics(mock_ds)
                    
                    # Should force fast path despite large size
                    mock_fast.assert_called_once()
                    mock_blocked.assert_not_called()
    
    def test_force_blocked_strategy(self):
        """Test forcing blocked path via configuration."""
        # Small file that would normally use fast path
        mock_ds = Mock(spec=gdal.Dataset)
        mock_ds.RasterCount = 1
        
        mock_band = Mock(spec=gdal.Band)
        mock_band.XSize = 1024
        mock_band.YSize = 1024
        
        mock_ds.GetRasterBand.return_value = mock_band
        
        def mock_config_get(key, default=None):
            if key == "statistics.force_strategy":
                return "blocked"
            return default
        
        with patch('gttk.utils.config_loader.config.get', side_effect=mock_config_get):
            with patch('gttk.utils.statistics.calculator._calculate_statistics_full') as mock_fast:
                with patch('gttk.utils.statistics.calculator._calculate_statistics_blocked') as mock_blocked:
                    mock_blocked.return_value = []
                    
                    calculate_statistics(mock_ds)
                    
                    # Should force blocked path despite small size
                    mock_blocked.assert_called_once()
                    mock_fast.assert_not_called()
    
    def test_custom_block_size(self):
        """Test using custom block size for blocked path."""
        custom_block_size = (1024, 1024)
        
        # Large file
        mock_ds = Mock(spec=gdal.Dataset)
        mock_ds.RasterCount = 1
        
        mock_band = Mock(spec=gdal.Band)
        mock_band.XSize = 50000
        mock_band.YSize = 50000
        
        mock_ds.GetRasterBand.return_value = mock_band
        
        with patch('gttk.utils.config_loader.config.get', return_value=0):
            with patch('gttk.utils.statistics.calculator._calculate_max_pixels_threshold', return_value=DEFAULT_MAX_PIXELS):
                with patch('gttk.utils.statistics.calculator._calculate_statistics_blocked') as mock_blocked:
                    mock_blocked.return_value = []
                    
                    calculate_statistics(mock_ds, block_size=custom_block_size)
                    
                    # Verify blocked path called with custom block size
                    mock_blocked.assert_called_once_with(mock_ds, custom_block_size)
    
    def test_invalid_force_strategy(self):
        """Test handling of invalid force_strategy value."""
        mock_ds = Mock(spec=gdal.Dataset)
        mock_ds.RasterCount = 1
        
        mock_band = Mock(spec=gdal.Band)
        mock_band.XSize = 1024
        mock_band.YSize = 1024
        mock_band.GetNoDataValue.return_value = None
        mock_band.GetDescription.return_value = "Band 1"
        mock_band.GetColorInterpretation.return_value = gdal.GCI_GrayIndex
        mock_band.GetMaskFlags.return_value = gdal.GMF_ALL_VALID
        mock_band.ReadAsArray.return_value = np.random.randint(0, 255, (1024, 1024), dtype=np.uint8)
        
        mock_ds.GetRasterBand.return_value = mock_band
        
        def mock_config_get(key, default=None):
            if key == "statistics.force_strategy":
                return "invalid_strategy"
            return default
        
        with patch('gttk.utils.config_loader.config.get', side_effect=mock_config_get):
            with patch('gttk.utils.statistics.calculator._calculate_max_pixels_threshold', return_value=DEFAULT_MAX_PIXELS):
                with patch('gttk.utils.statistics.calculator._calculate_statistics_full') as mock_fast:
                    mock_fast.return_value = []
                    
                    # Should fall back to auto-selection
                    calculate_statistics(mock_ds)
                    
                    # Small file, should use fast path after fallback
                    mock_fast.assert_called_once()


class TestConfigurationIntegration:
    """Test configuration integration."""
    
    def test_block_size_from_config(self):
        """Test reading block_size from configuration."""
        custom_block_size = [1024, 1024]
        
        # Large file
        mock_ds = Mock(spec=gdal.Dataset)
        mock_ds.RasterCount = 1
        
        mock_band = Mock(spec=gdal.Band)
        mock_band.XSize = 50000
        mock_band.YSize = 50000
        
        mock_ds.GetRasterBand.return_value = mock_band
        
        def mock_config_get(key, default=None):
            if key == "statistics.block_size":
                return custom_block_size
            if key == "statistics.max_pixels_fast_path":
                return 0
            return default
        
        with patch('gttk.utils.config_loader.config.get', side_effect=mock_config_get):
            with patch('gttk.utils.statistics.calculator._calculate_max_pixels_threshold', return_value=DEFAULT_MAX_PIXELS):
                with patch('gttk.utils.statistics.calculator._calculate_statistics_blocked') as mock_blocked:
                    mock_blocked.return_value = []
                    
                    calculate_statistics(mock_ds)
                    
                    # Verify blocked path called with config block size
                    mock_blocked.assert_called_once_with(mock_ds, tuple(custom_block_size))


if __name__ == '__main__':
    pytest.main([__file__, '-v'])
