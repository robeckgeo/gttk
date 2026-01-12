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
Test Fixtures for Statistics Optimization Testing.

Contains reference implementations and helper functions for validating
optimized statistics calculations.
"""

import numpy as np


class OnlineStatisticsOriginal:
    """
    Original Welford's algorithm implementation for validation.
    
    This class preserves the original per-pixel iteration logic
    for comparison testing against the optimized vectorized implementation.
    
    Used exclusively for testing to verify numerical accuracy of
    optimizations. DO NOT use in production code (extremely slow).
    
    References:
        - Welford, B. P. (1962). "Note on a method for calculating corrected
          sums of squares and products". Technometrics. 4(3): 419-420.
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
        Update statistics with new block of data using Welford's algorithm.
        
        This is the ORIGINAL SLOW implementation that iterates over
        every pixel in Python. Kept only for validation testing.
        
        Args:
            block: NumPy array of values (should be float64 for precision)
        """
        if block.size == 0:
            return
        
        # Update min/max
        block_min = np.min(block)
        block_max = np.max(block)
        self.min_val = min(self.min_val, block_min)
        self.max_val = max(self.max_val, block_max)
        
        # Welford's algorithm (SLOW - per-pixel iteration)
        for value in block.flat:
            self.count += 1
            delta = value - self.mean
            self.mean += delta / self.count
            delta2 = value - self.mean
            self.m2 += delta * delta2
    
    def finalize(self) -> dict:
        """
        Calculate final statistics from accumulated values.
        
        Returns:
            Dictionary with keys: count, minimum, maximum, mean, std_dev
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
