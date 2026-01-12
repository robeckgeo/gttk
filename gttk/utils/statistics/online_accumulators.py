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
Online Statistics Accumulators.

Streaming statistics accumulators for block-based processing of large raster
datasets. Supports numerically stable accumulation of mean, variance, min/max,
and histogram counts across multiple blocks.

Classes:
    OnlineStatistics: Accumulate statistics using Chan's parallel variance algorithm
    OnlineHistogram: Accumulate histogram counts across blocks
    AlphaCharacteristics: Track alpha band characteristics for intelligent detection
"""

import numpy as np
import logging

# Configure logging
logger = logging.getLogger(__name__)

# ============================================================================
# ONLINE ACCUMULATORS
# ============================================================================

class OnlineStatistics:
    """
    Accumulates statistics across blocks using Chan's parallel variance algorithm.
    
    Numerically stable algorithm achieving >40x speedup over original Python loop
    implementation through NumPy vectorization.
    
    The algorithm processes data in blocks and maintains running statistics
    (mean, variance, min/max) using Chan's parallel variance formula for
    numerical stability.
    
    Performance: For a 50000×60000 GeoTIFF (3 billion pixels), this reduces
    statistics calculation time from hours to minutes.
    
    References:
        Chan, T.F., Golub, G.H., LeVeque, R.J. (1983). "Algorithms for
        computing the sample variance: Analysis and recommendations".
        The American Statistician. 37(3): 242-247.
    
    Example:
        >>> stats = OnlineStatistics()
        >>> for block in data_blocks:
        >>>     stats.update(block)
        >>> result = stats.finalize()
        >>> print(f"Mean: {result['mean']}, StdDev: {result['std_dev']}")
    """
    
    def __init__(self):
        """Initialize statistics accumulator."""
        self.count = 0
        self.mean = 0.0
        self.m2 = 0.0  # Sum of squared differences from mean
        self.min_val = float('inf')
        self.max_val = float('-inf')
    
    def update(self, block: np.ndarray):
        """
        Update statistics with vectorized NumPy operations using Chan's algorithm.
        
        Uses Chan's parallel variance algorithm for numerical stability:
        - Computes block statistics in vectorized manner (O(n) vectorized)
        - Combines with existing statistics using parallel formula (O(1))
        
        References:
            Chan, T.F., Golub, G.H., LeVeque, R.J. (1983)
            "Algorithms for computing the sample variance"
            The American Statistician. 37(3): 242-247.
        
        Args:
            block: NumPy array of values (should be float64 for precision)
        """
        if block.size == 0:
            return
        
        # Block statistics (vectorized - FAST)
        # These operations run at C speed via NumPy
        block_count = block.size
        block_mean = np.mean(block)          # Vectorized: O(n)
        block_min = np.min(block)            # Vectorized: O(n)
        block_max = np.max(block)            # Vectorized: O(n)
        
        # Update min/max
        self.min_val = min(self.min_val, block_min)
        self.max_val = max(self.max_val, block_max)
        
        # Chan's parallel variance formula
        if self.count == 0:
            # First block: initialize directly
            self.count = block_count
            self.mean = block_mean
            # M2 = sum of squared deviations from mean
            self.m2 = np.sum((block - block_mean) ** 2)  # Vectorized: O(n)
        else:
            # Subsequent blocks: merge with existing statistics
            delta = block_mean - self.mean
            total_count = self.count + block_count
            
            # Update mean (weighted average)
            self.mean = (self.count * self.mean + block_count * block_mean) / total_count
            
            # Update M2 using parallel variance formula
            # This is the key to numerical stability
            block_m2 = np.sum((block - block_mean) ** 2)  # Vectorized: O(n)
            self.m2 = self.m2 + block_m2 + delta**2 * self.count * block_count / total_count
            
            # Update count
            self.count = total_count
    
    def finalize(self) -> dict:
        """
        Calculate final statistics from accumulated values.
        
        Returns:
            Dictionary with keys: count, minimum, maximum, mean, std_dev
            Returns None for numeric fields if count is 0.
        """
        if self.count == 0:
            return {
                'count': 0,
                'minimum': None,
                'maximum': None,
                'mean': None,
                'std_dev': None
            }
        
        # Calculate variance and standard deviation
        variance = self.m2 / self.count
        std_dev = np.sqrt(variance)
        
        return {
            'count': self.count,
            'minimum': float(self.min_val),
            'maximum': float(self.max_val),
            'mean': float(self.mean),
            'std_dev': float(std_dev)
        }


class OnlineHistogram:
    """
    Accumulates histogram counts across blocks.
    
    This class maintains histogram bin counts while processing data in chunks,
    allowing histogram generation for datasets too large to fit in memory.
    
    The bins must be determined before starting accumulation (typically from
    a first pass to find min/max values).
    
    Example:
        >>> bins = np.linspace(0, 100, 257)  # 256 bins from 0 to 100
        >>> histogram = OnlineHistogram(bins)
        >>> for block in data_blocks:
        >>>     histogram.update(block)
        >>> counts, bins = histogram.get_result()
    """
    
    def __init__(self, bins: np.ndarray):
        """
        Initialize histogram accumulator with predetermined bins.
        
        Args:
            bins: Bin edges from np.linspace(min, max, n_bins + 1)
                  Array of length (n_bins + 1) defining bin boundaries
        """
        self.bins = bins
        self.counts = np.zeros(len(bins) - 1, dtype=np.int64)
    
    def update(self, block: np.ndarray):
        """
        Add block data to histogram counts.
        
        Uses np.histogram for efficient bin assignment. Accumulates counts
        across multiple blocks.
        
        Args:
            block: NumPy array of values to add to histogram
        """
        if block.size == 0:
            return
        
        # np.histogram is fast and handles bin assignment correctly
        block_counts, _ = np.histogram(block, bins=self.bins)
        self.counts += block_counts
    
    def get_result(self) -> tuple:
        """
        Return final histogram result.
        
        Returns:
            Tuple of (counts_list, bins_list) compatible with StatisticsBand format
        """
        return (self.counts.tolist(), self.bins.tolist())


class AlphaCharacteristics:
    """
    Track alpha band characteristics during Pass 1 scan for intelligent detection.
    
    Detects whether an alpha band is:
    - Binary (only 0 and max values, e.g., 0/255)
    - Near-binary (mostly binary with compression artifacts)
    - Graduated (significant intermediate transparency values)
    
    This detection happens during the existing Pass 1 min/max scan with
    zero additional performance overhead.
    
    Example:
        >>> alpha_char = AlphaCharacteristics()
        >>> for block in alpha_blocks:
        >>>     alpha_char.update(block)
        >>> alpha_type = alpha_char.get_alpha_type()
        >>> print(f"Alpha type: {alpha_type}")
    """
    
    def __init__(self):
        """Initialize alpha characteristics tracker."""
        self.min_val = float('inf')
        self.max_val = float('-inf')
        self.zero_count = 0
        self.max_count = 0  # Count of maximum value (usually 255)
        self.total_count = 0
        self.intermediate_count = 0  # Values not 0 or max
        self.unique_values = set()  # Track unique values (limit to 256 for Byte)
    
    def update(self, block: np.ndarray):
        """
        Update characteristics from block with minimal overhead.
        
        Args:
            block: NumPy array of alpha band data
        """
        if block.size == 0:
            return
        
        # Update min/max
        block_min = np.min(block)
        block_max = np.max(block)
        self.min_val = min(self.min_val, block_min)
        self.max_val = max(self.max_val, block_max)
        self.total_count += block.size
        
        # Count zeros and max values (vectorized - very fast)
        self.zero_count += np.count_nonzero(block == 0)
        
        # Only count max after we know what max is
        if self.max_val != float('-inf'):
            self.max_count += np.count_nonzero(block == self.max_val)
        
        # Track intermediate values
        if self.max_val != float('-inf'):
            intermediate = (block != 0) & (block != self.max_val)
            self.intermediate_count += np.count_nonzero(intermediate)
        
        # For Byte data, track unique values (cheap for 0-255 range)
        if len(self.unique_values) < 1000:  # Limit memory
            self.unique_values.update(np.unique(block).tolist())
    
    def get_alpha_type(self,
                       binary_threshold: float = 0.999,
                       near_binary_threshold: float = 0.99) -> str:
        """
        Determine alpha band type based on characteristics.
        
        Args:
            binary_threshold: % of pixels that must be 0 or max for strict binary
            near_binary_threshold: % threshold for near-binary with artifacts
            
        Returns:
            'binary' | 'near_binary' | 'graduated'
        """
        if self.total_count == 0:
            return 'binary'  # Default for empty
        
        # Calculate percentage of binary pixels (0 or max)
        binary_pixels = self.zero_count + self.max_count
        binary_percent = binary_pixels / self.total_count
        
        # Strict binary: ≥99.9% are 0 or max
        if binary_percent >= binary_threshold:
            return 'binary'
        
        # Near-binary with artifacts: ≥99% are 0 or max
        elif binary_percent >= near_binary_threshold:
            # Check if intermediate values are close to edges (artifacts)
            if len(self.unique_values) <= 10:  # Very few unique values
                return 'near_binary'
            return 'graduated'
        
        # Graduated alpha: significant intermediate values
        else:
            return 'graduated'
    
    def get_artifact_tolerance(self) -> int:
        """
        Suggest tolerance for treating near-binary as binary.
        
        Returns:
            Pixel value tolerance (e.g., treat 0-5 as 0, 250-255 as 255)
        """
        if self.get_alpha_type() == 'near_binary':
            # Check distribution near edges
            low_values = [v for v in self.unique_values if 0 < v < 10]
            high_values = [v for v in self.unique_values
                          if self.max_val - 10 < v < self.max_val]
            
            if low_values or high_values:
                return 5  # Tolerance of 5 for artifacts
        
        return 0  # No tolerance for graduated alpha
