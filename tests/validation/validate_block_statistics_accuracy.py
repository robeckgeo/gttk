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
Standalone validation script for block-based statistics accuracy.

This script validates that the OnlineStatistics class produces results
identical to NumPy's built-in functions, demonstrating the numerical
stability and accuracy of Welford's algorithm.

Run directly: python tests/validation/validate_block_statistics_accuracy.py
"""

import numpy as np
import sys
from gttk.utils.statistics import OnlineStatistics


def validate_simple_data():
    """Test with simple integer data."""
    print("=" * 70)
    print("TEST 1: Simple Integer Data")
    print("=" * 70)
    
    data = np.array([1.0, 2.0, 3.0, 4.0, 5.0], dtype=np.float64)
    
    # NumPy reference
    np_mean = np.mean(data)
    np_std = np.std(data)
    np_min = np.min(data)
    np_max = np.max(data)
    
    # OnlineStatistics
    stats = OnlineStatistics()
    stats.update(data)
    result = stats.finalize()
    
    print(f"Data: {data}")
    print("\nNumPy Results:")
    print(f"  Mean:   {np_mean:.10f}")
    print(f"  StdDev: {np_std:.10f}")
    print(f"  Min:    {np_min:.10f}")
    print(f"  Max:    {np_max:.10f}")
    
    print("\nOnlineStatistics Results:")
    print(f"  Mean:   {result['mean']:.10f}")
    print(f"  StdDev: {result['std_dev']:.10f}")
    print(f"  Min:    {result['minimum']:.10f}")
    print(f"  Max:    {result['maximum']:.10f}")
    
    print("\nDifferences:")
    print(f"  Mean:   {abs(result['mean'] - np_mean):.2e}")
    print(f"  StdDev: {abs(result['std_dev'] - np_std):.2e}")
    
    # Validate
    assert np.isclose(result['mean'], np_mean, rtol=1e-10), "Mean mismatch!"
    assert np.isclose(result['std_dev'], np_std, rtol=1e-10), "StdDev mismatch!"
    assert result['minimum'] == np_min, "Min mismatch!"
    assert result['maximum'] == np_max, "Max mismatch!"
    
    print("\n✅ PASSED: Results match NumPy within floating-point precision")


def validate_large_values():
    """Test with large values (numerical stability check)."""
    print("\n" + "=" * 70)
    print("TEST 2: Large Values (Numerical Stability)")
    print("=" * 70)
    
    # Large values that can cause numerical issues with naive algorithms
    data = np.array([1e10, 1e10 + 1, 1e10 + 2, 1e10 + 3, 1e10 + 4], dtype=np.float64)
    
    # NumPy reference
    np_mean = np.mean(data)
    np_std = np.std(data)
    
    # OnlineStatistics
    stats = OnlineStatistics()
    stats.update(data)
    result = stats.finalize()
    
    print("Data: values around 1e10")
    print("\nNumPy Results:")
    print(f"  Mean:   {np_mean:.10f}")
    print(f"  StdDev: {np_std:.10f}")
    
    print("\nOnlineStatistics Results:")
    print(f"  Mean:   {result['mean']:.10f}")
    print(f"  StdDev: {result['std_dev']:.10f}")
    
    print("\nDifferences:")
    print(f"  Mean:   {abs(result['mean'] - np_mean):.2e}")
    print(f"  StdDev: {abs(result['std_dev'] - np_std):.2e}")
    
    # Validate
    assert np.isclose(result['mean'], np_mean, rtol=1e-10), "Mean mismatch!"
    assert np.isclose(result['std_dev'], np_std, rtol=1e-10), "StdDev mismatch!"
    
    print("\n✅ PASSED: Welford's algorithm maintains numerical stability")


def validate_block_processing():
    """Test statistics accumulated across multiple blocks."""
    print("\n" + "=" * 70)
    print("TEST 3: Multi-Block Processing")
    print("=" * 70)
    
    # Create multiple blocks simulating block-based file reading
    np.random.seed(42)
    blocks = [
        np.random.rand(100, 100).astype(np.float64),
        np.random.rand(100, 100).astype(np.float64),
        np.random.rand(100, 100).astype(np.float64),
        np.random.rand(100, 100).astype(np.float64)
    ]
    
    print("Processing 4 blocks of 100×100 pixels each (40,000 total pixels)")
    
    # NumPy reference (all data at once)
    all_data = np.concatenate([b.ravel() for b in blocks])
    np_mean = np.mean(all_data)
    np_std = np.std(all_data)
    np_min = np.min(all_data)
    np_max = np.max(all_data)
    
    # OnlineStatistics (block by block)
    stats = OnlineStatistics()
    for i, block in enumerate(blocks, 1):
        stats.update(block)
        print(f"  Processed block {i}/4...")
    
    result = stats.finalize()
    
    print("\nNumPy Results (all data at once):")
    print(f"  Count:  {len(all_data):,}")
    print(f"  Mean:   {np_mean:.10f}")
    print(f"  StdDev: {np_std:.10f}")
    print(f"  Min:    {np_min:.10f}")
    print(f"  Max:    {np_max:.10f}")
    
    print("\nOnlineStatistics Results (block by block):")
    print(f"  Count:  {result['count']:,}")
    print(f"  Mean:   {result['mean']:.10f}")
    print(f"  StdDev: {result['std_dev']:.10f}")
    print(f"  Min:    {result['minimum']:.10f}")
    print(f"  Max:    {result['maximum']:.10f}")
    
    print("\nDifferences:")
    print(f"  Mean:   {abs(result['mean'] - np_mean):.2e}")
    print(f"  StdDev: {abs(result['std_dev'] - np_std):.2e}")
    
    # Validate
    assert result['count'] == len(all_data), "Count mismatch!"
    assert np.isclose(result['mean'], np_mean, rtol=1e-10), "Mean mismatch!"
    assert np.isclose(result['std_dev'], np_std, rtol=1e-10), "StdDev mismatch!"
    assert np.isclose(result['minimum'], np_min, rtol=1e-10), "Min mismatch!"
    assert np.isclose(result['maximum'], np_max, rtol=1e-10), "Max mismatch!"
    
    print("\n✅ PASSED: Block-based processing produces identical results")


def validate_realistic_geotiff_scenario():
    """Simulate realistic GeoTIFF processing scenario."""
    print("\n" + "=" * 70)
    print("TEST 4: Realistic GeoTIFF Scenario")
    print("=" * 70)
    
    # Simulate a large image processed in blocks
    # Image: 1024×1024 pixels, processed in 256×256 blocks
    np.random.seed(123)
    full_image = np.random.normal(100.0, 15.0, (1024, 1024)).astype(np.float64)
    
    print("Image size: 1024×1024 pixels")
    print("Block size: 256×256 pixels")
    print("Total blocks: 16 (4×4 grid)")
    
    # NumPy reference
    np_mean = np.mean(full_image)
    np_std = np.std(full_image)
    np_min = np.min(full_image)
    np_max = np.max(full_image)
    
    # OnlineStatistics with block iteration
    stats = OnlineStatistics()
    block_size = 256
    blocks_processed = 0
    
    for y in range(0, 1024, block_size):
        for x in range(0, 1024, block_size):
            block = full_image[y:y+block_size, x:x+block_size]
            stats.update(block)
            blocks_processed += 1
    
    result = stats.finalize()
    
    print(f"\nProcessed {blocks_processed} blocks")
    print("\nNumPy Results:")
    print(f"  Mean:   {np_mean:.6f}")
    print(f"  StdDev: {np_std:.6f}")
    print(f"  Min:    {np_min:.6f}")
    print(f"  Max:    {np_max:.6f}")
    
    print("\nOnlineStatistics Results:")
    print(f"  Mean:   {result['mean']:.6f}")
    print(f"  StdDev: {result['std_dev']:.6f}")
    print(f"  Min:    {result['minimum']:.6f}")
    print(f"  Max:    {result['maximum']:.6f}")
    
    print("\nDifferences:")
    print(f"  Mean:   {abs(result['mean'] - np_mean):.2e}")
    print(f"  StdDev: {abs(result['std_dev'] - np_std):.2e}")
    
    # Validate
    assert np.isclose(result['mean'], np_mean, rtol=1e-10), "Mean mismatch!"
    assert np.isclose(result['std_dev'], np_std, rtol=1e-10), "StdDev mismatch!"
    assert np.isclose(result['minimum'], np_min, rtol=1e-10), "Min mismatch!"
    assert np.isclose(result['maximum'], np_max, rtol=1e-10), "Max mismatch!"
    
    print("\n✅ PASSED: Realistic block processing maintains accuracy")


def main():
    """Run all validation tests."""
    print("\n" + "=" * 70)
    print("VALIDATING BLOCK-BASED STATISTICS ACCURACY")
    print("=" * 70)
    print("\nThis script validates that the OnlineStatistics implementation")
    print("produces results identical to NumPy's reference implementations,")
    print("demonstrating the numerical stability of Welford's algorithm.")
    print()
    
    try:
        validate_simple_data()
        validate_large_values()
        validate_block_processing()
        validate_realistic_geotiff_scenario()
        
        print("\n" + "=" * 70)
        print("✅ ALL VALIDATION TESTS PASSED")
        print("=" * 70)
        print("\nThe OnlineStatistics implementation:")
        print("  ✓ Matches NumPy results within floating-point precision")
        print("  ✓ Maintains numerical stability with large values")
        print("  ✓ Produces identical results for block-based processing")
        print("  ✓ Works correctly in realistic GeoTIFF scenarios")
        print("\nPhase 3 implementation is validated and ready for production use.")
        print()
        
        return 0
        
    except AssertionError as e:
        print(f"\n❌ VALIDATION FAILED: {e}")
        return 1
    except Exception as e:
        print(f"\n❌ ERROR: {e}")
        import traceback
        traceback.print_exc()
        return 1


if __name__ == "__main__":
    sys.exit(main())
