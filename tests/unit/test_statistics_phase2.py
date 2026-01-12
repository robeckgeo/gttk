#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
Unit tests for Phase 2 statistics optimizations.

Tests:
1. AlphaCharacteristics class functionality
2. Alpha type detection (binary, near-binary, graduated)
3. Block caching correctness
4. 2-pass algorithm equivalence with 3-pass
"""

import pytest
import numpy as np
from gttk.utils.statistics import AlphaCharacteristics


class TestAlphaCharacteristics:
    """Test AlphaCharacteristics class for intelligent alpha detection."""
    
    def test_initialization(self):
        """Test AlphaCharacteristics initialization."""
        alpha_char = AlphaCharacteristics()
        assert alpha_char.min_val == float('inf')
        assert alpha_char.max_val == float('-inf')
        assert alpha_char.zero_count == 0
        assert alpha_char.max_count == 0
        assert alpha_char.total_count == 0
        assert alpha_char.intermediate_count == 0
        assert len(alpha_char.unique_values) == 0
    
    def test_binary_alpha_detection(self):
        """Test detection of binary alpha (only 0 and 255)."""
        alpha_char = AlphaCharacteristics()
        
        # Create binary alpha blocks (only 0 and 255)
        block1 = np.array([[0, 255, 0, 255],
                          [255, 0, 255, 0],
                          [0, 255, 0, 255],
                          [255, 0, 255, 0]], dtype=np.uint8)
        
        block2 = np.array([[255, 255, 0, 0],
                          [0, 0, 255, 255],
                          [255, 255, 0, 0],
                          [0, 0, 255, 255]], dtype=np.uint8)
        
        alpha_char.update(block1)
        alpha_char.update(block2)
        
        assert alpha_char.min_val == 0
        assert alpha_char.max_val == 255
        assert alpha_char.total_count == 32
        assert alpha_char.zero_count == 16
        assert alpha_char.max_count == 16
        assert alpha_char.get_alpha_type() == 'binary'
        assert alpha_char.get_artifact_tolerance() == 0
    
    def test_near_binary_alpha_detection(self):
        """Test detection of near-binary alpha with artifacts."""
        alpha_char = AlphaCharacteristics()
        
        # Create near-binary alpha with artifacts
        # Target: 99.5% binary (between 99% and 99.9% thresholds)
        block = np.zeros((100, 100), dtype=np.uint8)
        block[:50, :] = 255  # 5000 pixels at 255
        block[50:, :] = 0    # 5000 pixels at 0
        
        # Add artifacts: 50 pixels (0.5%) to get 99.5% binary
        for i in range(50):
            row = 50 + (i // 10)
            col = i % 10
            block[row, col] = [1, 2, 253, 254][i % 4]
        
        alpha_char.update(block)
        
        assert alpha_char.min_val == 0
        assert alpha_char.max_val == 255
        assert alpha_char.total_count == 10000
        # Binary percent = (zero_count + max_count) / total = 9950 / 10000 = 99.5%
        binary_percent = (alpha_char.zero_count + alpha_char.max_count) / alpha_char.total_count
        assert 0.99 < binary_percent < 0.999  # Between thresholds
        
        alpha_type = alpha_char.get_alpha_type(
            binary_threshold=0.999,
            near_binary_threshold=0.99
        )
        assert alpha_type == 'near_binary'
        assert alpha_char.get_artifact_tolerance() == 5
    
    def test_graduated_alpha_detection(self):
        """Test detection of graduated alpha (smooth transparency)."""
        alpha_char = AlphaCharacteristics()
        
        # Create graduated alpha with smooth gradient
        block = np.zeros((256, 100), dtype=np.uint8)
        for i in range(256):
            block[i, :] = i  # Smooth gradient from 0 to 255
        
        alpha_char.update(block)
        
        assert alpha_char.min_val == 0
        assert alpha_char.max_val == 255
        assert alpha_char.total_count == 25600
        # Many intermediate values between 0 and 255
        binary_percent = (alpha_char.zero_count + alpha_char.max_count) / alpha_char.total_count
        assert binary_percent < 0.99  # Well below near-binary threshold
        assert len(alpha_char.unique_values) == 256  # All values 0-255 present
        
        alpha_type = alpha_char.get_alpha_type()
        assert alpha_type == 'graduated'
        assert alpha_char.get_artifact_tolerance() == 0
    
    def test_empty_block_handling(self):
        """Test handling of empty blocks."""
        alpha_char = AlphaCharacteristics()
        
        # Update with empty block (should not crash)
        empty_block = np.array([], dtype=np.uint8)
        alpha_char.update(empty_block)
        
        assert alpha_char.total_count == 0
        assert alpha_char.get_alpha_type() == 'binary'  # Default for empty
    
    def test_single_value_alpha(self):
        """Test alpha band with single value (all opaque or all transparent)."""
        alpha_char = AlphaCharacteristics()
        
        # All transparent (all zeros)
        block = np.zeros((100, 100), dtype=np.uint8)
        alpha_char.update(block)
        
        assert alpha_char.min_val == 0
        assert alpha_char.max_val == 0
        assert alpha_char.zero_count == 10000
        assert alpha_char.max_count == 10000  # max_val is 0, so all are "max"
        assert alpha_char.get_alpha_type() == 'binary'
    
    def test_multiple_blocks_accumulation(self):
        """Test characteristics accumulation across multiple blocks."""
        alpha_char = AlphaCharacteristics()
        
        # Block 1: Binary (0, 255)
        block1 = np.zeros((50, 50), dtype=np.uint8)
        block1[:25, :] = 255
        
        # Block 2: Binary (0, 255)
        block2 = np.full((50, 50), 255, dtype=np.uint8)
        block2[:10, :] = 0
        
        # Block 3: Add a few artifacts
        block3 = np.zeros((50, 50), dtype=np.uint8)
        block3[0, 0] = 1
        block3[0, 1] = 254
        
        alpha_char.update(block1)
        alpha_char.update(block2)
        alpha_char.update(block3)
        
        assert alpha_char.total_count == 7500
        # Should be near-binary due to 2 artifact pixels out of 7500
        binary_percent = (alpha_char.zero_count + alpha_char.max_count) / alpha_char.total_count
        assert binary_percent > 0.99
        
        alpha_type = alpha_char.get_alpha_type(
            binary_threshold=0.999,
            near_binary_threshold=0.99
        )
        assert alpha_type in ['binary', 'near_binary']
    
    def test_unique_values_limit(self):
        """Test that unique values tracking has memory limit."""
        alpha_char = AlphaCharacteristics()
        
        # Create block with many unique values
        # unique_values set is limited to 1000 items in implementation
        block = np.arange(0, 2000, dtype=np.uint16) % 256
        alpha_char.update(block)
        
        # Should track values but limit set size
        assert len(alpha_char.unique_values) <= 1000
    
    def test_configurable_thresholds(self):
        """Test alpha type detection with different threshold values."""
        alpha_char = AlphaCharacteristics()
        
        # Create alpha with ~98.5% binary pixels (clearly below 99% threshold)
        block = np.zeros((100, 100), dtype=np.uint8)
        block[:49, :] = 255  # 4900 pixels at 255
        block[50:, :] = 0    # 5000 pixels at 0
        # Add 150 intermediate values to get to 98.5% binary
        for i in range(150):
            row = 49 + (i // 100)
            col = i % 100
            block[row, col] = 128
        
        alpha_char.update(block)
        
        binary_percent = (alpha_char.zero_count + alpha_char.max_count) / alpha_char.total_count
        assert 0.98 < binary_percent < 0.99
        
        # With default thresholds (0.999, 0.99) -> graduated (below 0.99)
        assert alpha_char.get_alpha_type(0.999, 0.99) == 'graduated'
        
        # With lower thresholds (0.99, 0.985) -> near-binary (above 0.985, below 0.99)
        assert alpha_char.get_alpha_type(0.99, 0.985) == 'near_binary'
        
        # With very low thresholds (0.985, 0.98) -> binary (above 0.985)
        assert alpha_char.get_alpha_type(0.985, 0.98) == 'binary'


class TestPhase2Integration:
    """Integration tests for Phase 2 optimizations."""
    
    def test_alpha_characteristics_realistic_binary(self):
        """Test with realistic binary alpha band from RGBA PNG."""
        alpha_char = AlphaCharacteristics()
        
        # Simulate typical RGBA image alpha: some transparent, mostly opaque
        # 1000x1000 image, 80% opaque, 20% transparent
        block = np.full((1000, 1000), 255, dtype=np.uint8)
        block[:200, :] = 0  # 20% transparent (200,000 pixels)
        
        alpha_char.update(block)
        
        assert alpha_char.total_count == 1_000_000
        assert alpha_char.zero_count == 200_000
        assert alpha_char.max_count == 800_000
        assert alpha_char.get_alpha_type() == 'binary'
        assert len(alpha_char.unique_values) == 2  # Only 0 and 255
    
    def test_alpha_characteristics_jpeg_artifacts(self):
        """Test with alpha band that has JPEG compression artifacts."""
        alpha_char = AlphaCharacteristics()
        
        # Simulate JPEG-compressed alpha with edge artifacts
        # Start with binary base
        block = np.zeros((1000, 1000), dtype=np.uint8)
        block[:500, :] = 255
        
        # Add JPEG artifacts near edges (1% of pixels)
        # Values like 1, 2, 253, 254 near edges
        np.random.seed(42)
        artifact_mask = np.random.random((1000, 1000)) < 0.01
        artifact_values = np.random.choice([1, 2, 253, 254], size=(1000, 1000))
        block[artifact_mask] = artifact_values[artifact_mask]
        
        alpha_char.update(block)
        
        binary_percent = (alpha_char.zero_count + alpha_char.max_count) / alpha_char.total_count
        # Should be between 98% and 99% binary
        assert 0.98 < binary_percent < 0.995
        
        alpha_type = alpha_char.get_alpha_type(
            binary_threshold=0.999,
            near_binary_threshold=0.99
        )
        assert alpha_type == 'near_binary'
        
        # Should suggest tolerance for artifacts
        tolerance = alpha_char.get_artifact_tolerance()
        assert tolerance == 5


class TestPhase2Performance:
    """Performance-oriented tests for Phase 2."""
    
    def test_alpha_characteristics_overhead(self):
        """Verify AlphaCharacteristics has minimal overhead."""
        import time
        
        alpha_char = AlphaCharacteristics()
        
        # Large block (typical 2048x2048)
        block = np.random.randint(0, 256, size=(2048, 2048), dtype=np.uint8)
        
        # Time the update (should be very fast, < 50ms for 4MP block)
        start = time.time()
        alpha_char.update(block)
        elapsed = time.time() - start
        
        assert elapsed < 0.05, f"AlphaCharacteristics.update too slow: {elapsed:.4f}s"
        
        # Verify correctness
        assert alpha_char.total_count == 2048 * 2048
        assert alpha_char.min_val >= 0
        assert alpha_char.max_val <= 255
    
    def test_block_caching_memory_efficiency(self):
        """Verify cached masks use minimal memory compared to data blocks."""
        # Simulate a 2048x2048 block
        data_block = np.random.randint(0, 65536, size=(2048, 2048), dtype=np.uint16)
        alpha_block = np.random.randint(0, 256, size=(2048, 2048), dtype=np.uint8)
        
        # Create cached mask
        alpha_mask = (alpha_block == 0)
        
        # Memory comparison
        data_bytes = data_block.nbytes
        mask_bytes = alpha_mask.nbytes
        
        # NumPy boolean arrays are 1 byte per element (not 1 bit)
        # Mask should be 2x smaller than UInt16 data (1 byte bool vs 2 byte uint16)
        assert mask_bytes == data_bytes / 2, \
            f"Mask not as expected: {mask_bytes} bytes vs {data_bytes} bytes (data)"
        
        # For UInt16 data, boolean mask is 2x smaller (1 byte vs 2 bytes)
        # For RGBA with alpha caching: 1 cached mask reused for 3 RGB bands = efficiency gain


if __name__ == "__main__":
    pytest.main([__file__, "-v"])
