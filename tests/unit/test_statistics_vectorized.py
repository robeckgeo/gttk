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
Unit Tests for Vectorized Statistics Implementation.

Tests the vectorized OnlineStatistics implementation using Chan's parallel
variance algorithm against the original Welford's per-pixel implementation
to ensure numerical accuracy and correctness.
"""

import numpy as np
import pytest
from gttk.utils.statistics import OnlineStatistics
from tests.fixtures.statistics_helpers import OnlineStatisticsOriginal


class TestVectorizedStatisticsAccuracy:
    """Test that vectorized implementation matches original."""
    
    def test_single_block_accuracy(self):
        """Verify accuracy with single block."""
        np.random.seed(42)
        data = np.random.randn(10000).astype(np.float64)
        
        # Original
        stats_orig = OnlineStatisticsOriginal()
        stats_orig.update(data)
        result_orig = stats_orig.finalize()
        
        # Vectorized
        stats_vec = OnlineStatistics()
        stats_vec.update(data)
        result_vec = stats_vec.finalize()
        
        # Compare
        assert result_orig['count'] == result_vec['count']
        assert abs(result_orig['mean'] - result_vec['mean']) < 1e-10
        assert abs(result_orig['std_dev'] - result_vec['std_dev']) < 1e-9
        assert abs(result_orig['minimum'] - result_vec['minimum']) < 1e-10
        assert abs(result_orig['maximum'] - result_vec['maximum']) < 1e-10
    
    def test_multiple_blocks_accuracy(self):
        """Verify accuracy with multiple blocks."""
        np.random.seed(123)
        # Generate 1M values, process in 100 blocks
        data = np.random.randn(1000000).astype(np.float64)
        blocks = np.array_split(data, 100)
        
        # Original
        stats_orig = OnlineStatisticsOriginal()
        for block in blocks:
            stats_orig.update(block)
        result_orig = stats_orig.finalize()
        
        # Vectorized
        stats_vec = OnlineStatistics()
        for block in blocks:
            stats_vec.update(block)
        result_vec = stats_vec.finalize()
        
        # Compare
        assert result_orig['count'] == result_vec['count']
        assert abs(result_orig['mean'] - result_vec['mean']) < 1e-10
        assert abs(result_orig['std_dev'] - result_vec['std_dev']) < 1e-8
        assert abs(result_orig['minimum'] - result_vec['minimum']) < 1e-10
        assert abs(result_orig['maximum'] - result_vec['maximum']) < 1e-10
    
    def test_varying_block_sizes(self):
        """Test with blocks of different sizes."""
        np.random.seed(456)
        # Create blocks of varying sizes
        block_sizes = [100, 1000, 50, 5000, 200]
        
        # Generate data for each block
        blocks = [np.random.randn(size).astype(np.float64) for size in block_sizes]
        
        # Original
        stats_orig = OnlineStatisticsOriginal()
        for block in blocks:
            stats_orig.update(block)
        result_orig = stats_orig.finalize()
        
        # Vectorized
        stats_vec = OnlineStatistics()
        for block in blocks:
            stats_vec.update(block)
        result_vec = stats_vec.finalize()
        
        # Compare
        assert result_orig['count'] == result_vec['count']
        assert abs(result_orig['mean'] - result_vec['mean']) < 1e-10
        assert abs(result_orig['std_dev'] - result_vec['std_dev']) < 1e-9


class TestVectorizedStatisticsEdgeCases:
    """Test edge cases and special conditions."""
    
    def test_empty_block(self):
        """Handle empty blocks gracefully."""
        stats = OnlineStatistics()
        stats.update(np.array([]))
        result = stats.finalize()
        
        assert result['count'] == 0
        assert result['mean'] is None
        assert result['std_dev'] is None
        assert result['minimum'] is None
        assert result['maximum'] is None
    
    def test_single_value(self):
        """Handle single value correctly."""
        stats = OnlineStatistics()
        stats.update(np.array([42.0]))
        result = stats.finalize()
        
        assert result['count'] == 1
        assert result['mean'] == 42.0
        assert result['std_dev'] == 0.0
        assert result['minimum'] == 42.0
        assert result['maximum'] == 42.0
    
    def test_constant_values(self):
        """Handle constant values (zero variance)."""
        stats = OnlineStatistics()
        for _ in range(10):
            stats.update(np.full(1000, 5.0, dtype=np.float64))
        result = stats.finalize()
        
        assert result['count'] == 10000
        assert abs(result['mean'] - 5.0) < 1e-10
        assert result['std_dev'] < 1e-10  # Should be ~0
        assert result['minimum'] == 5.0
        assert result['maximum'] == 5.0
    
    def test_two_values(self):
        """Handle minimal case of two values."""
        stats = OnlineStatistics()
        stats.update(np.array([1.0, 3.0]))
        result = stats.finalize()
        
        assert result['count'] == 2
        assert result['mean'] == 2.0
        assert abs(result['std_dev'] - 1.0) < 1e-10
        assert result['minimum'] == 1.0
        assert result['maximum'] == 3.0
    
    def test_negative_values(self):
        """Handle negative values correctly."""
        np.random.seed(789)
        data = np.random.randn(5000).astype(np.float64) - 100  # Shift to negative
        
        stats = OnlineStatistics()
        stats.update(data)
        result = stats.finalize()
        
        assert result['count'] == 5000
        assert result['mean'] < 0  # Should be negative
        assert result['std_dev'] > 0
        assert result['minimum'] < result['mean']
        assert result['maximum'] > result['mean']
    
    def test_mixed_positive_negative(self):
        """Handle mix of positive and negative values."""
        data = np.array([-5.0, -3.0, 0.0, 3.0, 5.0], dtype=np.float64)
        
        stats = OnlineStatistics()
        stats.update(data)
        result = stats.finalize()
        
        assert result['count'] == 5
        assert abs(result['mean'] - 0.0) < 1e-10
        assert result['minimum'] == -5.0
        assert result['maximum'] == 5.0
    
    def test_empty_blocks_between_data(self):
        """Handle empty blocks interspersed with data."""
        stats = OnlineStatistics()
        
        # Add data
        stats.update(np.array([1.0, 2.0, 3.0]))
        # Add empty block
        stats.update(np.array([]))
        # Add more data
        stats.update(np.array([4.0, 5.0]))
        
        result = stats.finalize()
        
        assert result['count'] == 5
        assert result['mean'] == 3.0
        assert result['minimum'] == 1.0
        assert result['maximum'] == 5.0


class TestVectorizedStatisticsNumericalStability:
    """Test numerical stability with challenging data."""
    
    def test_large_values(self):
        """Test with large values (numerical stability)."""
        np.random.seed(101)
        # Large values can cause precision issues
        data = np.random.randn(100000).astype(np.float64) + 1e10
        blocks = np.array_split(data, 50)
        
        stats = OnlineStatistics()
        for block in blocks:
            stats.update(block)
        result = stats.finalize()
        
        # Compare with NumPy reference
        np_mean = np.mean(data)
        np_std = np.std(data)
        
        # Check relative error (more appropriate for large values)
        assert abs(result['mean'] - np_mean) / abs(np_mean) < 1e-8
        assert abs(result['std_dev'] - np_std) / np_std < 1e-6
    
    def test_small_values(self):
        """Test with very small values."""
        np.random.seed(202)
        data = np.random.randn(50000).astype(np.float64) * 1e-10
        blocks = np.array_split(data, 25)
        
        stats = OnlineStatistics()
        for block in blocks:
            stats.update(block)
        result = stats.finalize()
        
        # Compare with NumPy reference
        np_mean = np.mean(data)
        np_std = np.std(data)
        
        # For values near zero, use absolute error
        assert abs(result['mean'] - np_mean) < 1e-15
        assert abs(result['std_dev'] - np_std) < 1e-15
    
    def test_high_variance_data(self):
        """Test with data having high variance."""
        np.random.seed(303)
        # Mix of very different scales
        data1 = np.random.randn(10000).astype(np.float64)
        data2 = np.random.randn(10000).astype(np.float64) * 1000
        data = np.concatenate([data1, data2])
        
        blocks = np.array_split(data, 40)
        
        # Original
        stats_orig = OnlineStatisticsOriginal()
        for block in blocks:
            stats_orig.update(block)
        result_orig = stats_orig.finalize()
        
        # Vectorized
        stats_vec = OnlineStatistics()
        for block in blocks:
            stats_vec.update(block)
        result_vec = stats_vec.finalize()
        
        # Should still match
        assert abs(result_orig['mean'] - result_vec['mean']) < 1e-8
        assert abs(result_orig['std_dev'] - result_vec['std_dev']) < 1e-6


class TestVectorizedStatisticsDifferentDtypes:
    """Test with different numpy data types."""
    
    def test_uint8_data(self):
        """Test with uint8 data (typical for RGB images)."""
        np.random.seed(404)
        data = np.random.randint(0, 256, 10000, dtype=np.uint8)
        
        stats = OnlineStatistics()
        # Convert to float64 for statistics (as done in real usage)
        stats.update(data.astype(np.float64))
        result = stats.finalize()
        
        assert result['count'] == 10000
        assert 0 <= result['minimum'] <= 255
        assert 0 <= result['maximum'] <= 255
        assert result['mean'] is not None
        assert result['std_dev'] is not None
    
    def test_int16_data(self):
        """Test with int16 data."""
        np.random.seed(505)
        data = np.random.randint(-1000, 1000, 10000, dtype=np.int16)
        
        stats = OnlineStatistics()
        stats.update(data.astype(np.float64))
        result = stats.finalize()
        
        assert result['count'] == 10000
        assert -1000 <= result['minimum'] <= 1000
        assert -1000 <= result['maximum'] <= 1000
    
    def test_uint16_data(self):
        """Test with uint16 data (common for satellite imagery)."""
        np.random.seed(606)
        data = np.random.randint(0, 10000, 10000, dtype=np.uint16)
        
        stats = OnlineStatistics()
        stats.update(data.astype(np.float64))
        result = stats.finalize()
        
        assert result['count'] == 10000
        assert 0 <= result['minimum'] <= 10000
        assert 0 <= result['maximum'] <= 10000
    
    def test_float32_data(self):
        """Test with float32 data."""
        np.random.seed(707)
        data = np.random.randn(10000).astype(np.float32)
        
        stats = OnlineStatistics()
        stats.update(data.astype(np.float64))
        result = stats.finalize()
        
        assert result['count'] == 10000
        assert result['mean'] is not None
        assert result['std_dev'] is not None
    
    def test_float64_data(self):
        """Test with float64 data (native processing type)."""
        np.random.seed(808)
        data = np.random.randn(10000).astype(np.float64)
        
        stats = OnlineStatistics()
        stats.update(data)
        result = stats.finalize()
        
        assert result['count'] == 10000
        assert result['mean'] is not None
        assert result['std_dev'] is not None


class TestVectorizedStatisticsMultidimensionalBlocks:
    """Test with different array shapes."""
    
    def test_1d_array(self):
        """Test with 1D array."""
        np.random.seed(909)
        data = np.random.randn(10000).astype(np.float64)
        
        stats = OnlineStatistics()
        stats.update(data)
        result = stats.finalize()
        
        assert result['count'] == 10000
    
    def test_2d_array(self):
        """Test with 2D array (typical raster block)."""
        np.random.seed(1010)
        data = np.random.randn(100, 100).astype(np.float64)
        
        stats = OnlineStatistics()
        stats.update(data)
        result = stats.finalize()
        
        assert result['count'] == 10000
    
    def test_3d_array(self):
        """Test with 3D array (less common but possible)."""
        np.random.seed(1111)
        data = np.random.randn(10, 20, 50).astype(np.float64)
        
        stats = OnlineStatistics()
        stats.update(data)
        result = stats.finalize()
        
        assert result['count'] == 10000
    
    def test_mixed_shapes(self):
        """Test with blocks of different shapes."""
        np.random.seed(1212)
        
        stats = OnlineStatistics()
        stats.update(np.random.randn(1000).astype(np.float64))  # 1D
        stats.update(np.random.randn(50, 20).astype(np.float64))  # 2D
        stats.update(np.random.randn(10, 10, 10).astype(np.float64))  # 3D
        
        result = stats.finalize()
        
        assert result['count'] == 1000 + 1000 + 1000


class TestVectorizedStatisticsSequentialProperties:
    """Test properties of sequential block processing."""
    
    def test_order_independence(self):
        """Verify that block order doesn't affect final result."""
        np.random.seed(1313)
        blocks = [np.random.randn(1000).astype(np.float64) for _ in range(10)]
        
        # Process in original order
        stats1 = OnlineStatistics()
        for block in blocks:
            stats1.update(block)
        result1 = stats1.finalize()
        
        # Process in reverse order
        stats2 = OnlineStatistics()
        for block in reversed(blocks):
            stats2.update(block)
        result2 = stats2.finalize()
        
        # Results should be identical
        assert result1['count'] == result2['count']
        assert abs(result1['mean'] - result2['mean']) < 1e-10
        assert abs(result1['std_dev'] - result2['std_dev']) < 1e-10
        # Min/max might differ due to floating point, but should be close
        assert abs(result1['minimum'] - result2['minimum']) < 1e-10
        assert abs(result1['maximum'] - result2['maximum']) < 1e-10
    
    def test_incremental_vs_batch(self):
        """Compare incremental processing vs single batch."""
        np.random.seed(1414)
        data = np.random.randn(10000).astype(np.float64)
        
        # Process incrementally
        stats_inc = OnlineStatistics()
        blocks = np.array_split(data, 10)
        for block in blocks:
            stats_inc.update(block)
        result_inc = stats_inc.finalize()
        
        # Process as single batch
        stats_batch = OnlineStatistics()
        stats_batch.update(data)
        result_batch = stats_batch.finalize()
        
        # Should match within numerical precision
        assert result_inc['count'] == result_batch['count']
        assert abs(result_inc['mean'] - result_batch['mean']) < 1e-10
        assert abs(result_inc['std_dev'] - result_batch['std_dev']) < 1e-10
        assert abs(result_inc['minimum'] - result_batch['minimum']) < 1e-10
        assert abs(result_inc['maximum'] - result_batch['maximum']) < 1e-10


if __name__ == "__main__":
    pytest.main([__file__, "-v"])
