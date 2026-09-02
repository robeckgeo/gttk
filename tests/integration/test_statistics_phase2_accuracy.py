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
The blocked statistics path against NumPy and against the fast path.

``tests/validation/validate_phase2_accuracy.py`` was written to show that the two-pass
blocked algorithm (Phase 2 of the statistics work) reproduces the results of the
three-pass one it replaced. Nothing ran it, and what it checked when run by hand was
only that each statistic existed and that min <= mean <= max; the comparison function
it defined was never called. Here the same four rasters -- RGBA Byte with a binary
alpha, RGB Byte, RGBA UInt16 with NoData, and a Float32 band with NoData -- are compared
against an in-memory NumPy reference wherever the masking rule is plain, and against
the fast path in every case: the two paths read the same pixels by different routes
and must agree.
"""

import numpy as np
import pytest
from osgeo import gdal

from gttk.utils.statistics import _calculate_statistics_blocked, _calculate_statistics_full

pytestmark = pytest.mark.integration

SIZE = 512
BLOCK = (128, 128)
TRANSPARENT_ROWS = SIZE // 5

CASES = {
    'rgba_byte_binary_alpha': dict(bands=4, data_type=gdal.GDT_Byte, alpha=True, nodata=None),
    'rgb_byte': dict(bands=3, data_type=gdal.GDT_Byte, alpha=False, nodata=None),
    'rgba_uint16_nodata': dict(bands=4, data_type=gdal.GDT_UInt16, alpha=True, nodata=0),
    'float32_nodata': dict(bands=1, data_type=gdal.GDT_Float32, alpha=False, nodata=-9999),
}
WITH_ALPHA = [name for name, case in CASES.items() if case['alpha']]
WITHOUT_ALPHA = [name for name, case in CASES.items() if not case['alpha']]


def _write(path, bands, data_type, alpha, nodata, seed=42):
    """Build the raster the validation script built, and return its arrays band by band."""
    rng = np.random.default_rng(seed)
    ds = gdal.GetDriverByName('GTiff').Create(
        str(path), SIZE, SIZE, bands, data_type,
        options=['TILED=YES', 'BLOCKXSIZE=256', 'BLOCKYSIZE=256', 'COMPRESS=LZW'])
    arrays = []
    for index in range(1, bands + 1):
        band = ds.GetRasterBand(index)
        if data_type == gdal.GDT_Byte:
            data = rng.integers(0, 256, size=(SIZE, SIZE), dtype=np.uint8)
        elif data_type == gdal.GDT_UInt16:
            data = rng.integers(0, 65536, size=(SIZE, SIZE), dtype=np.uint16)
        else:
            data = (rng.standard_normal((SIZE, SIZE)) * 100).astype(np.float32)
        if nodata is not None:
            data[rng.random((SIZE, SIZE)) < 0.1] = nodata
            band.SetNoDataValue(float(nodata))
        if alpha and index == bands:
            data = np.full((SIZE, SIZE), 255, dtype=data.dtype)
            data[:TRANSPARENT_ROWS, :] = 0
            band.SetColorInterpretation(gdal.GCI_AlphaBand)
        elif index <= 3:
            band.SetColorInterpretation(gdal.GCI_RedBand + index - 1)
        band.WriteArray(data)
        arrays.append(data)
    ds.FlushCache()
    return ds, arrays


@pytest.fixture(params=list(CASES), ids=list(CASES))
def raster(request, tmp_path):
    ds, arrays = _write(tmp_path / f'{request.param}.tif', **CASES[request.param])
    yield request.param, ds, arrays
    ds = None


class TestBlockedPathAccuracy:

    def test_agrees_with_the_fast_path(self, raster):
        name, ds, _ = raster
        blocked = _calculate_statistics_blocked(ds, block_size=BLOCK)
        fast = _calculate_statistics_full(ds)
        assert blocked is not None and fast is not None and len(blocked) == len(fast) == CASES[name]['bands']
        for index, (b, f) in enumerate(zip(blocked, fast), 1):
            assert b.valid_count == f.valid_count, f'band {index} valid_count'
            assert b.nodata_count == f.nodata_count, f'band {index} nodata_count'
            for field in ('minimum', 'maximum', 'mean', 'std_dev'):
                blocked_value, fast_value = getattr(b, field), getattr(f, field)
                assert blocked_value is not None and fast_value is not None, f'band {index} {field}'
                assert np.isclose(blocked_value, fast_value, rtol=1e-6), f'band {index} {field}'

    def test_matches_numpy_where_the_mask_is_the_nodata_value(self, raster):
        """No alpha band: a pixel counts unless it holds the NoData value."""
        name, ds, arrays = raster
        if CASES[name]['alpha']:
            pytest.skip('alpha rasters are covered by the fast-path comparison')
        nodata = CASES[name]['nodata']
        for index, (stats, data) in enumerate(zip(_calculate_statistics_blocked(ds, block_size=BLOCK), arrays), 1):
            valid = data.astype(np.float64) if nodata is None else data[data != nodata].astype(np.float64)
            assert stats.valid_count == valid.size, f'band {index}'
            assert stats.minimum == valid.min() and stats.maximum == valid.max(), f'band {index}'
            assert np.isclose(stats.mean, valid.mean(), rtol=1e-8), f'band {index}'
            assert np.isclose(stats.std_dev, valid.std(), rtol=1e-8), f'band {index}'

    def test_transparent_pixels_leave_the_colour_bands(self, raster):
        name, ds, arrays = raster
        if not CASES[name]['alpha']:
            pytest.skip('no alpha band')
        alpha = arrays[-1]
        nodata = CASES[name]['nodata']
        transparent = SIZE * TRANSPARENT_ROWS
        for index, (stats, data) in enumerate(zip(_calculate_statistics_blocked(ds, block_size=BLOCK), arrays[:-1]), 1):
            assert stats.alpha_0_count == transparent, f'band {index}'
            valid = (alpha != 0) if nodata is None else (alpha != 0) & (data != nodata)
            assert stats.valid_count == int(valid.sum()), f'band {index}'
            values = data[valid].astype(np.float64)
            assert np.isclose(stats.mean, values.mean(), rtol=1e-8), f'band {index}'
