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
The output does not depend on where the intermediates were held.

`gttk optimize` built its intermediates in GDAL's ``/vsimem`` whatever their size. For a
91,445 x 53,704 four-band orthophoto that is about 36 GB of them -- on a 16 GB machine,
the pagefile, and every pass after it reads its own pixels back through the swapper
instead of GDAL's block cache. The workspace now sizes them from the input and writes them
beside the output when they will not fit.

That is a change of location, so what matters is that it is only a change of location:
these run the same raster both ways and compare the bytes that come out.
"""

import hashlib

import numpy as np
import pytest
from osgeo import gdal, osr

import gttk.utils.preprocessor as preprocessor
import gttk.tools.optimize_compression as ocmp
from gttk.utils.script_arguments import OptimizeArguments

pytestmark = pytest.mark.integration


@pytest.fixture
def rgba(tmp_path):
    """RGBA, so the run builds both intermediates: the tiled copy and the masked one."""
    path = tmp_path / 'image.tif'
    ds = gdal.GetDriverByName('GTiff').Create(str(path), 512, 512, 4, gdal.GDT_Byte, options=['TILED=YES'])
    ds.SetGeoTransform((500000, 1, 0, 4000000, 0, -1))
    srs = osr.SpatialReference(); srs.ImportFromEPSG(32610)
    ds.SetProjection(srs.ExportToWkt())
    rng = np.random.default_rng(5)
    for index in range(1, 5):
        band = ds.GetRasterBand(index)
        band.SetColorInterpretation(gdal.GCI_RedBand + index - 1 if index < 4 else gdal.GCI_AlphaBand)
        if index == 4:
            alpha = np.full((512, 512), 255, np.uint8); alpha[:100, :] = 0
            band.WriteArray(alpha)
        else:
            band.WriteArray(rng.integers(0, 256, (512, 512), dtype=np.uint8))
    ds.FlushCache()
    return path


def _digests(source, out_dir, name, **overrides):
    output = out_dir / f'{name}.tif'
    kwargs = dict(input_path=source, output_path=output, product_type='image', algorithm='JPEG',
                  quality=90, report=False, open_report=False, arc_mode=True)
    kwargs.update(overrides)
    assert ocmp.optimize_compression(OptimizeArguments(**kwargs)) != 1
    sidecar = out_dir / f'{name}.tif.aux.xml'
    return (hashlib.md5(output.read_bytes()).hexdigest(),
            hashlib.md5(sidecar.read_bytes()).hexdigest())


class TestEitherLocationGivesTheSameFile:

    def test_disk_and_memory_agree(self, rgba, tmp_path, monkeypatch):
        in_memory = _digests(rgba, tmp_path, 'memory')
        monkeypatch.setattr(preprocessor, 'workspace_fits_in_memory', lambda *a, **kw: False)
        on_disk = _digests(rgba, tmp_path, 'disk')
        assert on_disk == in_memory

    def test_a_disk_run_leaves_nothing_behind(self, rgba, tmp_path, monkeypatch):
        """The intermediates are beside the output; a run that forgot them would leave
        tens of gigabytes in the user's data directory."""
        monkeypatch.setattr(preprocessor, 'workspace_fits_in_memory', lambda *a, **kw: False)
        _digests(rgba, tmp_path, 'disk')
        assert sorted(p.name for p in tmp_path.iterdir()) == ['disk.tif', 'disk.tif.aux.xml', 'image.tif']

    def test_a_memory_run_leaves_nothing_in_vsimem(self, rgba, tmp_path):
        _digests(rgba, tmp_path, 'memory')
        assert [n for n in (gdal.ReadDirRecursive('/vsimem/') or []) if 'compress_' in n] == []
