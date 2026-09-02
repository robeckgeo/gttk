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
The ArcGIS optimize path, run for real on Linux through a fake OSGeo4W tree.

``optimize_compression_arc`` builds a sequence of GDAL commands and generated Python
scripts and has ``gdal_runner`` execute them under OSGeo4W's interpreter. It was 9%
covered: its orchestration ran only inside ArcGIS Pro, and the one test that reached its
entry point asserted substrings of its source. With the tree from
``tests/fixtures/fake_osgeo4w`` the whole route runs here -- gdalinfo, the NoData remap,
the rounding scripts, gdaladdo, the final translate -- with the real GDAL.
"""

import os
from pathlib import Path

import pytest
from osgeo import gdal, osr

import gttk.tools.optimize_compression_arc as oc
from gttk.utils.config_loader import config
from gttk.utils.script_arguments import OptimizeArguments
from tests.fixtures.fake_osgeo4w import build_fake_osgeo4w
from tests.fixtures.mock_geotiff_factory import MockGeoTIFF

pytestmark = [pytest.mark.integration,
              pytest.mark.skipif(os.name == 'nt', reason='the fake OSGeo4W is POSIX-only; Windows has the real one')]


@pytest.fixture(scope='module')
def osgeo4w(tmp_path_factory):
    return build_fake_osgeo4w(tmp_path_factory.mktemp('OSGeo4W'))


@pytest.fixture
def configured(osgeo4w, monkeypatch):
    monkeypatch.setattr(config, 'get', lambda key, default=None: str(osgeo4w) if key == 'paths.osgeo4w' else default)
    return osgeo4w


def _dem(path: Path) -> Path:
    MockGeoTIFF(width=128, height=128, data_type=gdal.GDT_Float32, crs='EPSG:32610',
                nodata_value=-9999.0).save_to_file(path)
    return path


def _optimize(input_path: Path, output_path: Path, **overrides) -> int:
    kwargs = dict(input_path=input_path, output_path=output_path, product_type='dem',
                  vertical_srs='EPSG:5703', report=False, open_report=False, write_pam_xml=True)
    kwargs.update(overrides)
    return oc.optimize_compression(OptimizeArguments(**kwargs))


class TestDemThroughTheTree:

    def test_becomes_a_cog_with_a_compound_crs_and_statistics(self, configured, tmp_path):
        source, out = _dem(tmp_path / 'dem.tif'), tmp_path / 'dem_cog.tif'
        assert _optimize(source, out) == 0
        ds = gdal.Open(str(out))
        assert ds.GetMetadataItem('LAYOUT', 'IMAGE_STRUCTURE') == 'COG'
        assert ds.GetMetadataItem('COMPRESSION', 'IMAGE_STRUCTURE') == 'DEFLATE'
        srs = osr.SpatialReference(wkt=ds.GetProjection())
        assert srs.IsCompound(), ds.GetProjection()[:80]
        assert ds.GetRasterBand(1).GetOverviewCount() >= 1
        assert (tmp_path / 'dem_cog.tif.aux.xml').exists()

    def test_an_input_named_like_a_python_statement(self, configured, tmp_path):
        """Every generated script used to embed this name in its source."""
        source = _dem(tmp_path / 'x"; open("MARKER", "w").close() #.tif')
        out = tmp_path / 'out.tif'
        assert _optimize(source, out) == 0
        assert out.exists() and not (tmp_path / 'MARKER').exists()


class TestImageThroughTheTree:

    def test_an_rgba_image_gets_an_internal_mask(self, configured, tmp_path):
        """The alpha band goes through gdal_calc.py and the mask-attachment script."""
        source, out = tmp_path / 'rgba.tif', tmp_path / 'rgba_cog.tif'
        MockGeoTIFF(width=128, height=128, bands=4, data_type=gdal.GDT_Byte, crs='EPSG:32610').save_to_file(source)
        assert _optimize(source, out, product_type='image', vertical_srs=None) == 0
        ds = gdal.Open(str(out))
        assert ds.GetMetadataItem('LAYOUT', 'IMAGE_STRUCTURE') == 'COG'
        assert ds.GetRasterBand(1).GetMaskFlags() & gdal.GMF_PER_DATASET
