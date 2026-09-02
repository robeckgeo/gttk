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
OnlineStatistics against NumPy.

These four checks lived in ``tests/validation/validate_block_statistics_accuracy.py``,
a script nothing ran: pytest did not collect it and no document named it. They are
the direct evidence that Welford's algorithm, fed block by block, reproduces NumPy's
mean, standard deviation, minimum and maximum to 1e-10 -- the property every blocked
statistic in a report rests on -- so they run with the suite now.
"""

import numpy as np
import pytest

from gttk.utils.statistics import OnlineStatistics

pytestmark = pytest.mark.unit


def _online(*blocks):
    stats = OnlineStatistics()
    for block in blocks:
        stats.update(block)
    return stats.finalize()


def _assert_matches_numpy(result, data, rtol=1e-10):
    assert np.isclose(result['mean'], np.mean(data), rtol=rtol)
    assert np.isclose(result['std_dev'], np.std(data), rtol=rtol)
    assert result['minimum'] == np.min(data)
    assert result['maximum'] == np.max(data)


class TestOnlineStatisticsMatchesNumpy:

    def test_five_integers(self):
        data = np.array([1.0, 2.0, 3.0, 4.0, 5.0])
        _assert_matches_numpy(_online(data), data)

    def test_large_offsets_keep_their_variance(self):
        """A sum-of-squares formula loses the spread of values near 1e10 to cancellation."""
        data = np.array([1e10, 1e10 + 1, 1e10 + 2, 1e10 + 3, 1e10 + 4])
        _assert_matches_numpy(_online(data), data)

    def test_four_blocks_equal_one_array(self):
        rng = np.random.default_rng(42)
        blocks = [rng.random((100, 100)) for _ in range(4)]
        result = _online(*blocks)
        data = np.concatenate([block.ravel() for block in blocks])
        assert result['count'] == data.size
        _assert_matches_numpy(result, data)

    def test_an_image_read_in_square_blocks(self):
        """1024x1024 normal data through 16 blocks of 256x256, the way a tiled file is read."""
        rng = np.random.default_rng(123)
        image = rng.normal(100.0, 15.0, (1024, 1024))
        blocks = [image[y:y + 256, x:x + 256] for y in range(0, 1024, 256) for x in range(0, 1024, 256)]
        result = _online(*blocks)
        assert result['count'] == image.size
        _assert_matches_numpy(result, image)
