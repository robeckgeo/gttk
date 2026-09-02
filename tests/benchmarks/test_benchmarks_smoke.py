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
Every benchmark, run once at a small size.

The benchmarks are a hand-run tool: their default sizes take minutes and gigabytes, and
nothing else imported them, so the functions they call could change under them without
anyone noticing until the next time someone ran the script by hand -- and its docstring
named a module that did not exist. Each benchmark takes its sizes as parameters now and
returns what it measured; these tests run each at 256x256 and check that a number comes
back, or for the alpha classifier, the right label.
"""

import pytest

from tests.benchmarks import benchmark_optimize as optimize_bench
from tests.benchmarks import benchmark_statistics as bench

pytestmark = pytest.mark.integration


def test_online_statistics_throughput():
    results = bench.benchmark_online_statistics_throughput(sizes=(256,))
    assert len(results) == 1 and results[0]['throughput'] > 0 and results[0]['speedup'] > 0


def test_online_histogram_accumulation():
    [(bins, rate)] = bench.benchmark_online_histogram_accumulation(block_size=256, bin_configs=(16,))
    assert bins == 16 and rate > 0


def test_full_path():
    [(size, rate)] = bench.benchmark_calculate_statistics_full_path(sizes=(256,))
    assert size == 256 and rate > 0


def test_blocked_path():
    assert bench.benchmark_calculate_statistics_blocked_path(size=256, block=64) > 0


def test_alpha_characteristics_overhead():
    [(size, rate)] = bench.benchmark_alpha_characteristics_overhead(sizes=(256,))
    assert size == 256 and rate > 0


def test_alpha_type_detection_classifies_all_three():
    assert bench.benchmark_alpha_type_detection_accuracy(size=256) == {
        'Binary (0/255 only)': 'binary',
        'Near-binary (0.5% artifacts)': 'near_binary',
        'Graduated (smooth)': 'graduated',
    }


def test_block_caching_efficiency():
    assert bench.benchmark_block_caching_efficiency() == 3


def test_optimal_block_size():
    results = bench.benchmark_optimal_block_size(size=256, block_sizes=(64, 128))
    assert [block for block, _ in results] == [64, 128] and all(rate > 0 for _, rate in results)


def test_rgba_imagery():
    assert bench.benchmark_rgba_imagery(size=256, block=64) > 0


def test_large_dem():
    assert bench.benchmark_large_dem(size=256, block=64) > 0


class TestOptimizeBenchmarks:
    """``benchmark_optimize``: what one optimize run costs. Its defaults build an 8192x8192
    raster three times over, so the suite runs each at 256x256 -- the numbers are noise at
    that size, the code paths are not."""

    def test_statistics_passes(self):
        results = optimize_bench.benchmark_statistics_passes(size=256)
        assert results['write only'][0] == 1, 'the write should take one statistics pass'
        assert results['with report'][0] == 3
        assert all(seconds > 0 for _, _, seconds in results.values())

    def test_workspace_location(self):
        results = optimize_bench.benchmark_workspace_location(size=256)
        assert results['memory'] > 0 and results['disk'] > 0
        assert results['estimated_gb'] == 256 * 256 * 4 * 2 / 1024 ** 3

    def test_end_to_end(self):
        assert optimize_bench.benchmark_end_to_end(size=256) > 0
