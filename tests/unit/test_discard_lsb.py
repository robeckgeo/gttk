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
Unit tests for the DISCARD_LSB decimals->bits helper and the test-harness
accuracy metrics (compute_error_metrics).
"""

import math

import numpy as np
import pytest
from osgeo import gdal

from gttk.utils.optimize_constants import discard_lsb_bits_for
from gttk.utils.accuracy_metrics import compute_error_metrics
from gttk.main import parse_decimals


@pytest.mark.unit
class TestDiscardLsbBits:
    """The decimals -> mantissa-bits formula and its guards."""

    @pytest.mark.parametrize("decimals,vmax,expected", [
        (2, 4000, 5),      # ~1 cm precision, topo magnitudes
        (2, 50, 11),       # small magnitudes allow more bits
        (8, 4000, 0),      # tight precision + large magnitude -> nothing safe to clear
        (2, 0, 0),         # guard: zero magnitude
        (2, None, 0),      # guard: missing magnitude
        (None, 4000, 0),   # guard: missing decimals
        (2, -4000, 5),     # uses |magnitude|
    ])
    def test_expected_bits(self, decimals, vmax, expected):
        assert discard_lsb_bits_for(decimals, vmax) == expected

    def test_clamped_to_float32_mantissa(self):
        # Very small magnitude would allow a huge bit count; must clamp to [0, 23].
        assert 0 <= discard_lsb_bits_for(2, 1e-6) <= 23

    @pytest.mark.parametrize("decimals,vmax", [
        (2, 4000.0), (3, 120.0), (1, 9000.0), (2, 30.0), (4, 1.0),
    ])
    def test_precision_guarantee(self, decimals, vmax):
        """Clearing K bits must keep worst-case abs error <= 0.5*10^-decimals at vmax.

        GDAL DISCARD_LSB rounds to nearest, so the worst-case error for a value of
        exponent E after clearing K mantissa bits is 2**(E-24+K).
        """
        k = discard_lsb_bits_for(decimals, vmax)
        if k == 0:
            pytest.skip("no bits cleared for this (decimals, vmax)")
        e = math.floor(math.log2(vmax))
        worst_case_error = 2 ** (e - 24 + k)
        assert worst_case_error <= 0.5 * 10 ** -decimals + 1e-30

    def test_more_bits_for_smaller_magnitude(self):
        # Lower magnitude (same precision) should never allow fewer bits.
        assert discard_lsb_bits_for(2, 50) >= discard_lsb_bits_for(2, 4000)


def _write_vsimem(path, arr, nodata=None):
    ny, nx = arr.shape
    ds = gdal.GetDriverByName('GTiff').Create(path, nx, ny, 1, gdal.GDT_Float32)
    if nodata is not None:
        ds.GetRasterBand(1).SetNoDataValue(nodata)
    ds.GetRasterBand(1).WriteArray(arr)
    ds.FlushCache()
    ds = None


@pytest.mark.unit
class TestComputeErrorMetrics:
    """Accuracy metrics computed by gttk test against the original raster."""

    def test_lossless_roundtrip_is_zero_error(self):
        a = np.linspace(1, 100, 64 * 64, dtype=np.float32).reshape(64, 64)
        _write_vsimem('/vsimem/em_o.tif', a)
        _write_vsimem('/vsimem/em_c.tif', a)
        try:
            m = compute_error_metrics('/vsimem/em_o.tif', '/vsimem/em_c.tif')
        finally:
            gdal.Unlink('/vsimem/em_o.tif'); gdal.Unlink('/vsimem/em_c.tif')
        assert m is not None
        assert m['max_abs_error'] == 0.0
        assert m['rmse'] == 0.0
        assert m['pct_changed'] == 0.0

    def test_known_delta(self):
        a = np.zeros((32, 32), dtype=np.float32)
        b = a.copy()
        b[0, 0] = 0.5  # exactly one of 1024 pixels changes by 0.5
        _write_vsimem('/vsimem/em_o.tif', a)
        _write_vsimem('/vsimem/em_c.tif', b)
        try:
            m = compute_error_metrics('/vsimem/em_o.tif', '/vsimem/em_c.tif')
        finally:
            gdal.Unlink('/vsimem/em_o.tif'); gdal.Unlink('/vsimem/em_c.tif')
        assert m['max_abs_error'] == pytest.approx(0.5)
        assert m['rmse'] == pytest.approx((0.25 / 1024) ** 0.5)
        assert m['pct_changed'] == pytest.approx(100.0 / 1024)

    def test_nodata_is_ignored(self):
        a = np.ones((16, 16), dtype=np.float32)
        a[0, :] = -9999.0  # nodata row in the original
        b = a.copy()
        b[0, :] = 12345.0  # differs only within the original's nodata region
        _write_vsimem('/vsimem/em_o.tif', a, nodata=-9999.0)
        _write_vsimem('/vsimem/em_c.tif', b, nodata=-9999.0)
        try:
            m = compute_error_metrics('/vsimem/em_o.tif', '/vsimem/em_c.tif')
        finally:
            gdal.Unlink('/vsimem/em_o.tif'); gdal.Unlink('/vsimem/em_c.tif')
        assert m['max_abs_error'] == 0.0  # nodata-region differences excluded

    def test_mismatched_shape_returns_none(self):
        _write_vsimem('/vsimem/em_o.tif', np.ones((10, 10), dtype=np.float32))
        _write_vsimem('/vsimem/em_c.tif', np.ones((10, 11), dtype=np.float32))
        try:
            m = compute_error_metrics('/vsimem/em_o.tif', '/vsimem/em_c.tif')
        finally:
            gdal.Unlink('/vsimem/em_o.tif'); gdal.Unlink('/vsimem/em_c.tif')
        assert m is None


@pytest.mark.unit
class TestParseDecimals:
    """The --decimals argparse type: integer or the 'none' sentinel."""

    @pytest.mark.parametrize("raw,expected", [
        ('none', 'none'), ('NONE', 'none'), (' none ', 'none'), ('off', 'none'), ('keep', 'none'),
        ('0', 0), ('2', 2), ('12', 12),
    ])
    def test_valid(self, raw, expected):
        assert parse_decimals(raw) == expected

    @pytest.mark.parametrize("raw", ['-1', 'abc', '2.5', ''])
    def test_invalid_rejected(self, raw):
        import argparse
        with pytest.raises(argparse.ArgumentTypeError):
            parse_decimals(raw)
