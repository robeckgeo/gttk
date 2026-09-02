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
How many times ``gttk optimize`` reads the raster to compute statistics.

It used to be twice for the write: once at the end of ``preprocess_geotiff``, to put
STATISTICS_* band metadata on the intermediate, and once in the orchestrator for the
``.aux.xml``. The two computed the same numbers from the same pixels, and the first one's
product never reached the output -- it sat in a metadata domain that neither the COG
driver nor ``CreateCopy`` propagates, on a file deleted at the end of the run. On a
4.9 gigapixel orthophoto that was a quarter of an hour spent on nothing.

Statistics of a raster too large for memory cost one full read per pass and cannot be
made cheaper, so the count is the thing worth pinning.
"""

import numpy as np
import pytest
from osgeo import gdal, osr

import gttk.tools.optimize_compression as ocmp
from gttk.utils.script_arguments import OptimizeArguments

pytestmark = pytest.mark.unit


@pytest.fixture
def counted_statistics(monkeypatch):
    """Count the full statistics computations one optimize run makes.

    Counted at the two functions ``calculate_statistics`` dispatches to, rather than at
    ``calculate_statistics`` itself: every module that uses it bound the name at import,
    so patching one importer's name would miss the others -- which is how a two-pass
    pipeline could look like a one-pass pipeline to a test.
    """
    import gttk.utils.statistics.calculator as calculator
    calls = []
    for name in ('_calculate_statistics_full', '_calculate_statistics_blocked'):
        real = getattr(calculator, name)

        def counting(*args, _real=real, **kwargs):
            calls.append(1)
            return _real(*args, **kwargs)

        monkeypatch.setattr(calculator, name, counting)
    return calls


@pytest.fixture
def rgba(tmp_path):
    """A small RGBA raster: alpha makes the preprocessor build both intermediates."""
    path = tmp_path / 'image.tif'
    ds = gdal.GetDriverByName('GTiff').Create(str(path), 256, 256, 4, gdal.GDT_Byte, options=['TILED=YES'])
    ds.SetGeoTransform((500000, 1, 0, 4000000, 0, -1))
    srs = osr.SpatialReference(); srs.ImportFromEPSG(32610)
    ds.SetProjection(srs.ExportToWkt())
    rng = np.random.default_rng(11)
    for index in range(1, 5):
        band = ds.GetRasterBand(index)
        band.SetColorInterpretation(gdal.GCI_RedBand + index - 1 if index < 4 else gdal.GCI_AlphaBand)
        if index == 4:
            alpha = np.full((256, 256), 255, np.uint8); alpha[:50, :] = 0
            band.WriteArray(alpha)
        else:
            band.WriteArray(rng.integers(0, 256, (256, 256), dtype=np.uint8))
    ds.FlushCache()
    return path


def _optimize(source, output, **overrides):
    kwargs = dict(input_path=source, output_path=output, product_type='image', algorithm='LZW',
                  report=False, open_report=False, arc_mode=True)
    kwargs.update(overrides)
    return ocmp.optimize_compression(OptimizeArguments(**kwargs))


class TestPassCount:

    @pytest.mark.parametrize('cog', [True, False])
    def test_the_write_takes_one_pass(self, rgba, tmp_path, counted_statistics, cog):
        _optimize(rgba, tmp_path / 'out.tif', cog=cog, algorithm='JPEG' if cog else 'LZW')
        assert counted_statistics == [1]

    def test_the_report_is_what_adds_the_others(self, rgba, tmp_path, counted_statistics):
        """--report, on by default, reads the input and the output again. Those two are
        real work on different pixels -- the input still has its alpha band, the output has
        been through the codec -- so they can only be declined, not shared."""
        _optimize(rgba, tmp_path / 'out.tif', report=True)
        assert len(counted_statistics) == 3


class TestTheOutputStillCarriesThem:
    """What the single pass has to keep producing."""

    def test_the_sidecar_holds_the_statistics(self, rgba, tmp_path):
        out = tmp_path / 'out.tif'
        _optimize(rgba, out)
        sidecar = tmp_path / 'out.tif.aux.xml'
        assert sidecar.is_file()
        text = sidecar.read_text(encoding='utf-8')
        for key in ('STATISTICS_MINIMUM', 'STATISTICS_MAXIMUM', 'STATISTICS_MEAN', 'STATISTICS_STDDEV'):
            assert key in text, key

    def test_a_cog_carries_them_inside_the_file_too(self, rgba, tmp_path):
        """GDAL's own -stats on the final translate writes these; the sidecar is separate."""
        out = tmp_path / 'out.tif'
        _optimize(rgba, out, cog=True, algorithm='JPEG')
        gdal.SetConfigOption('GDAL_PAM_ENABLED', 'NO')
        try:
            ds = gdal.Open(str(out))
            inside = {k for k in (ds.GetRasterBand(1).GetMetadata() or {}) if k.startswith('STATISTICS_')}
            ds = None
        finally:
            gdal.SetConfigOption('GDAL_PAM_ENABLED', 'YES')
        assert {'STATISTICS_MINIMUM', 'STATISTICS_MAXIMUM', 'STATISTICS_MEAN'} <= inside
