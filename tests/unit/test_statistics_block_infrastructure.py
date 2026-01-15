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
Unit tests for block-based processing infrastructure.

Tests the OnlineStatistics, OnlineHistogram, and _iterate_blocks components
that enable memory-efficient processing of large GeoTIFF files.
"""

import pytest
import numpy as np
from osgeo import gdal
from gttk.utils.statistics import (
    OnlineStatistics,
    OnlineHistogram,
    _iterate_blocks,
)


class TestOnlineStatistics:
    """Tests for the OnlineStatistics class using Welford's algorithm."""
    
    def test_welford_algorithm_accuracy_simple(self):
        """Verify Welford's algorithm matches numpy for simple data."""
        # Create test data
        data = np.array([1.0, 2.0, 3.0, 4.0, 5.0], dtype=np.float64)
        
        # Calculate with numpy (reference)
        expected_mean = np.mean(data)
        expected_std = np.std(data)
        expected_min = np.min(data)
        expected_max = np.max(data)
        
        # Calculate with OnlineStatistics
        stats = OnlineStatistics()
        stats.update(data)
        result = stats.finalize()
        
        # Verify results match within floating-point precision
        assert result['count'] == 5
        assert np.isclose(result['mean'], expected_mean, rtol=1e-10)
        assert np.isclose(result['std_dev'], expected_std, rtol=1e-10)
        assert result['minimum'] == expected_min
        assert result['maximum'] == expected_max
    
    def test_welford_algorithm_accuracy_large_values(self):
        """Test Welford's algorithm with large values (numerical stability)."""
        # Large values that could cause numerical issues with naive algorithms
        data = np.array([1e10, 1e10 + 1, 1e10 + 2, 1e10 + 3], dtype=np.float64)
        
        expected_mean = np.mean(data)
        expected_std = np.std(data)
        
        stats = OnlineStatistics()
        stats.update(data)
        result = stats.finalize()
        
        assert np.isclose(result['mean'], expected_mean, rtol=1e-10)
        assert np.isclose(result['std_dev'], expected_std, rtol=1e-10)
    
    def test_online_statistics_single_block(self):
        """Test statistics on a single block."""
        block = np.random.rand(100, 100).astype(np.float64)
        
        stats = OnlineStatistics()
        stats.update(block)
        result = stats.finalize()
        
        assert result['count'] == 10000
        assert np.isclose(result['mean'], np.mean(block), rtol=1e-10)
        assert np.isclose(result['std_dev'], np.std(block), rtol=1e-10)
        assert np.isclose(result['minimum'], np.min(block), rtol=1e-10)
        assert np.isclose(result['maximum'], np.max(block), rtol=1e-10)
    
    def test_online_statistics_multiple_blocks(self):
        """Test statistics accumulated across multiple blocks."""
        # Create multiple blocks
        np.random.seed(42)
        blocks = [
            np.random.rand(50, 50).astype(np.float64),
            np.random.rand(50, 50).astype(np.float64),
            np.random.rand(50, 50).astype(np.float64),
            np.random.rand(50, 50).astype(np.float64)
        ]
        
        # Calculate statistics block by block
        stats = OnlineStatistics()
        for block in blocks:
            stats.update(block)
        result = stats.finalize()
        
        # Calculate reference statistics on combined data
        all_data = np.concatenate([b.ravel() for b in blocks])
        expected_mean = np.mean(all_data)
        expected_std = np.std(all_data)
        expected_min = np.min(all_data)
        expected_max = np.max(all_data)
        
        # Verify accumulated results match
        assert result['count'] == len(all_data)
        assert np.isclose(result['mean'], expected_mean, rtol=1e-10)
        assert np.isclose(result['std_dev'], expected_std, rtol=1e-10)
        assert np.isclose(result['minimum'], expected_min, rtol=1e-10)
        assert np.isclose(result['maximum'], expected_max, rtol=1e-10)
    
    def test_online_statistics_empty_block(self):
        """Test that empty blocks are handled gracefully."""
        stats = OnlineStatistics()
        empty_block = np.array([], dtype=np.float64)
        stats.update(empty_block)
        result = stats.finalize()
        
        assert result['count'] == 0
        assert result['mean'] is None
        assert result['std_dev'] is None
        assert result['minimum'] is None
        assert result['maximum'] is None
    
    def test_online_statistics_single_value(self):
        """Test statistics with single value (edge case for std dev)."""
        stats = OnlineStatistics()
        stats.update(np.array([42.0], dtype=np.float64))
        result = stats.finalize()
        
        assert result['count'] == 1
        assert result['mean'] == 42.0
        assert result['std_dev'] == 0.0
        assert result['minimum'] == 42.0
        assert result['maximum'] == 42.0
    
    def test_online_statistics_negative_values(self):
        """Test statistics with negative values."""
        data = np.array([-5.0, -3.0, -1.0, 1.0, 3.0, 5.0], dtype=np.float64)
        
        stats = OnlineStatistics()
        stats.update(data)
        result = stats.finalize()
        
        assert np.isclose(result['mean'], 0.0, atol=1e-10)
        assert result['minimum'] == -5.0
        assert result['maximum'] == 5.0


class TestOnlineHistogram:
    """Tests for the OnlineHistogram class."""
    
    def test_histogram_single_block(self):
        """Test histogram with a single block."""
        data = np.array([1.0, 2.0, 3.0, 4.0, 5.0], dtype=np.float64)
        bins = np.linspace(0, 6, 7)  # 6 bins: [0-1), [1-2), [2-3), [3-4), [4-5), [5-6)
        
        histogram = OnlineHistogram(bins)
        histogram.update(data)
        counts, bins_result = histogram.get_result()
        
        # Verify bins are preserved
        assert np.array_equal(bins_result, bins.tolist())
        
        # Verify counts: expect [0, 1, 1, 1, 1, 1]
        # (0 values in [0-1), 1 value in each other bin)
        expected_counts = [0, 1, 1, 1, 1, 1]
        assert counts == expected_counts
    
    def test_histogram_multiple_blocks(self):
        """Test histogram accumulated across multiple blocks."""
        bins = np.linspace(0, 10, 11)  # 10 bins
        
        # Create blocks with known distributions
        block1 = np.array([1.5, 2.5, 3.5], dtype=np.float64)
        block2 = np.array([1.5, 2.5, 3.5], dtype=np.float64)
        block3 = np.array([5.5, 6.5, 7.5], dtype=np.float64)
        
        histogram = OnlineHistogram(bins)
        histogram.update(block1)
        histogram.update(block2)
        histogram.update(block3)
        counts, _ = histogram.get_result()
        
        # Verify accumulated counts
        # bins: [0-1), [1-2), [2-3), [3-4), [4-5), [5-6), [6-7), [7-8), [8-9), [9-10)
        # block1: 1 in [1-2), 1 in [2-3), 1 in [3-4)
        # block2: 1 in [1-2), 1 in [2-3), 1 in [3-4)
        # block3: 1 in [5-6), 1 in [6-7), 1 in [7-8)
        expected_counts = [0, 2, 2, 2, 0, 1, 1, 1, 0, 0]
        assert counts == expected_counts
    
    def test_histogram_empty_block(self):
        """Test that empty blocks don't affect histogram."""
        bins = np.linspace(0, 10, 11)
        histogram = OnlineHistogram(bins)
        
        # Add empty block
        histogram.update(np.array([], dtype=np.float64))
        counts, _ = histogram.get_result()
        
        # Should be all zeros
        assert counts == [0] * 10
    
    def test_histogram_byte_data(self):
        """Test histogram with byte data (0-255)."""
        # Simulate RGB byte data
        data = np.array([0, 50, 100, 150, 200, 255], dtype=np.float64)
        bins = np.linspace(0, 256, 257)  # 256 bins for byte data
        
        histogram = OnlineHistogram(bins)
        histogram.update(data)
        counts, _ = histogram.get_result()
        
        # Each value should fall into its own bin
        assert sum(counts) == 6
        assert counts[0] == 1  # value 0
        assert counts[50] == 1  # value 50
        assert counts[255] == 1  # value 255


class TestIterateBlocks:
    """Tests for the _iterate_blocks generator function."""
    
    def test_block_iterator_coverage(self, tmp_path):
        """Ensure all pixels are visited exactly once."""
        # Create a test GeoTIFF with known pattern
        width, height = 100, 100
        driver = gdal.GetDriverByName('GTiff')
        filepath = str(tmp_path / "test_coverage.tif")
        
        dataset = driver.Create(filepath, width, height, 1, gdal.GDT_Byte)
        band = dataset.GetRasterBand(1)
        
        # Write sequential values (0 to 9999)
        data = np.arange(width * height, dtype=np.uint8).reshape(height, width)
        band.WriteArray(data)
        band.FlushCache()
        
        # Collect all block values
        collected_values = []
        block_size = (32, 32)  # Use non-divisible block size to test edges
        
        for block, x_off, y_off, x_sz, y_sz in _iterate_blocks(band, block_size):
            collected_values.extend(block.ravel().tolist())
        
        # Verify we got all pixels
        assert len(collected_values) == width * height
        
        # Verify we got each value exactly once
        collected_sorted = sorted(collected_values)
        expected_sorted = sorted(data.ravel().tolist())
        assert collected_sorted == expected_sorted
        
        dataset = None
    
    def test_block_iterator_edge_cases(self, tmp_path):
        """Test partial blocks at image edges."""
        # Create image with dimensions not divisible by block size
        width, height = 100, 75  # Non-square, non-divisible by common block sizes
        driver = gdal.GetDriverByName('GTiff')
        filepath = str(tmp_path / "test_edges.tif")
        
        dataset = driver.Create(filepath, width, height, 1, gdal.GDT_Float32)
        band = dataset.GetRasterBand(1)
        
        # Fill with known pattern
        data = np.ones((height, width), dtype=np.float32)
        band.WriteArray(data)
        band.FlushCache()
        
        # Iterate with block size that doesn't divide evenly
        block_size = (32, 32)
        total_pixels = 0
        blocks_read = 0
        
        for block, x_off, y_off, x_sz, y_sz in _iterate_blocks(band, block_size):
            blocks_read += 1
            total_pixels += block.size
            
            # Verify block dimensions don't exceed specified block_size
            assert block.shape[0] <= block_size[0]
            assert block.shape[1] <= block_size[1]
            
            # Verify block dimensions match reported sizes
            assert block.shape == (y_sz, x_sz)
            
            # Verify all values are 1.0
            assert np.all(block == 1.0)
        
        # Verify we processed all pixels
        assert total_pixels == width * height
        
        # Verify we had the expected number of blocks
        # (75 / 32 = 2 full + 1 partial row) * (100 / 32 = 3 full + 1 partial col)
        # = 3 rows * 4 cols = 12 blocks
        assert blocks_read == 12
        
        dataset = None
    
    def test_block_iterator_native_dtype(self, tmp_path):
        """Test that blocks are returned in native dtype."""
        driver = gdal.GetDriverByName('GTiff')
        filepath = str(tmp_path / "test_dtype.tif")
        
        # Test with UInt16 data
        dataset = driver.Create(filepath, 64, 64, 1, gdal.GDT_UInt16)
        band = dataset.GetRasterBand(1)
        
        data = np.arange(64 * 64, dtype=np.uint16).reshape(64, 64)
        band.WriteArray(data)
        band.FlushCache()
        
        # Iterate and check dtype
        for block, x_off, y_off, x_sz, y_sz in _iterate_blocks(band, (32, 32)):
            # Verify native dtype is preserved
            assert block.dtype == np.uint16
            
            # Verify values are correct
            expected_block = data[y_off:y_off+y_sz, x_off:x_off+x_sz]
            assert np.array_equal(block, expected_block)
        
        dataset = None
    
    def test_block_iterator_single_block(self, tmp_path):
        """Test iterator with image smaller than block size."""
        # Small image that fits in one block
        width, height = 50, 50
        driver = gdal.GetDriverByName('GTiff')
        filepath = str(tmp_path / "test_single.tif")
        
        dataset = driver.Create(filepath, width, height, 1, gdal.GDT_Byte)
        band = dataset.GetRasterBand(1)
        
        data = np.ones((height, width), dtype=np.uint8) * 42
        band.WriteArray(data)
        band.FlushCache()
        
        # Use large block size
        blocks = list(_iterate_blocks(band, (256, 256)))
        
        # Should get exactly one block
        assert len(blocks) == 1
        
        block, x_off, y_off, x_sz, y_sz = blocks[0]
        assert x_off == 0 and y_off == 0
        assert x_sz == width and y_sz == height
        assert np.all(block == 42)
        
        dataset = None


class TestBlockInfrastructureIntegration:
    """Integration tests combining multiple components."""
    
    def test_statistics_via_blocks(self, tmp_path):
        """Test calculating statistics using block iteration."""
        # Create test file
        width, height = 200, 200
        driver = gdal.GetDriverByName('GTiff')
        filepath = str(tmp_path / "test_integration.tif")
        
        dataset = driver.Create(filepath, width, height, 1, gdal.GDT_Float32)
        band = dataset.GetRasterBand(1)
        
        # Create data with known statistics
        np.random.seed(123)
        data = np.random.normal(100.0, 15.0, (height, width)).astype(np.float32)
        band.WriteArray(data)
        band.FlushCache()
        
        # Calculate reference statistics
        expected_mean = np.mean(data)
        expected_std = np.std(data)
        expected_min = np.min(data)
        expected_max = np.max(data)
        
        # Calculate statistics using block iteration
        stats = OnlineStatistics()
        for block, x_off, y_off, x_sz, y_sz in _iterate_blocks(band, (64, 64)):
            # Promote to float64 for statistics
            block_f64 = block.astype(np.float64)
            stats.update(block_f64)
        
        result = stats.finalize()
        
        # Verify results match
        assert result['count'] == width * height
        assert np.isclose(result['mean'], expected_mean, rtol=1e-6)
        assert np.isclose(result['std_dev'], expected_std, rtol=1e-6)
        assert np.isclose(result['minimum'], expected_min, rtol=1e-6)
        assert np.isclose(result['maximum'], expected_max, rtol=1e-6)
        
        dataset = None
    
    def test_histogram_via_blocks(self, tmp_path):
        """Test generating histogram using block iteration."""
        # Create test file with uniform distribution
        width, height = 150, 150
        driver = gdal.GetDriverByName('GTiff')
        filepath = str(tmp_path / "test_hist_integration.tif")
        
        dataset = driver.Create(filepath, width, height, 1, gdal.GDT_Byte)
        band = dataset.GetRasterBand(1)
        
        # Create data: repeating pattern 0-255
        data = np.tile(np.arange(256, dtype=np.uint8), (height * width // 256 + 1))
        data = data[:height * width].reshape(height, width)
        band.WriteArray(data)
        band.FlushCache()
        
        # Calculate reference histogram
        expected_counts, expected_bins = np.histogram(data, bins=np.linspace(0, 256, 257))
        
        # Calculate histogram using blocks
        bins = np.linspace(0, 256, 257)
        histogram = OnlineHistogram(bins)
        
        for block, x_off, y_off, x_sz, y_sz in _iterate_blocks(band, (50, 50)):
            histogram.update(block.astype(np.float64))
        
        counts, _ = histogram.get_result()
        
        # Verify histogram matches
        assert counts == expected_counts.tolist()
        
        dataset = None


if __name__ == "__main__":
    pytest.main([__file__, "-v"])
