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
The guards on `gttk optimize`'s arguments hold on the paths that reach them, and fail
loudly rather than quietly.

Two things were wrong. Nothing stopped `-o` from naming the input file, or the input
directory, so `gttk optimize` overwrote its input in place -- it exited 0 and the data
survived only because the pipeline stages through /vsimem/. And the single-band check for
DEM, error and thematic products caught its own ValueError and re-raised it only if the
message contained the words "Multi-band rasters", swallowed every other failure of
gdal.Open without a word, and leaked the dataset handle on the path that raised.
"""

import gc
import logging
import weakref

import pytest
from osgeo import gdal

import gttk.utils.script_arguments as sa
from gttk.utils.script_arguments import OptimizeArguments
from tests.fixtures.mock_geotiff_factory import MockGeoTIFF

pytestmark = pytest.mark.unit


@pytest.fixture
def dem(tmp_path):
    path = tmp_path / 'dem.tif'
    MockGeoTIFF(width=16, height=16, data_type=gdal.GDT_Float32, crs='EPSG:32610').save_to_file(path)
    return path


def _args(**kwargs):
    kwargs.setdefault('product_type', 'dem')
    kwargs.setdefault('vertical_srs', 'EPSG:5703')
    return OptimizeArguments(**kwargs)


class TestInPlaceIsRefused:

    def test_the_input_file_as_output(self, dem):
        with pytest.raises(ValueError, match='in place'):
            _args(input_path=dem, output_path=dem)

    def test_the_input_file_by_another_spelling(self, dem):
        with pytest.raises(ValueError, match='in place'):
            _args(input_path=dem, output_path=dem.parent / '.' / dem.name)

    def test_the_input_directory_as_output_directory(self, dem):
        with pytest.raises(ValueError, match='in place'):
            _args(input_path=dem.parent, output_path=dem.parent)

    def test_a_different_output_is_fine(self, dem, tmp_path):
        args = _args(input_path=dem, output_path=tmp_path / 'out.tif')
        assert args.output_path == tmp_path / 'out.tif'


class TestSingleBandGuard:

    def test_a_multiband_raster_is_refused_for_a_dem(self, tmp_path):
        rgb = tmp_path / 'rgb.tif'
        MockGeoTIFF(width=16, height=16, bands=3, data_type=gdal.GDT_Byte, crs='EPSG:32610').save_to_file(rgb)
        with pytest.raises(ValueError, match='3 bands'):
            _args(input_path=rgb, output_path=tmp_path / 'out.tif')

    def test_a_value_error_propagates_whatever_it_says(self, dem, tmp_path, monkeypatch):
        """The guard used to re-raise only when the text said 'Multi-band rasters'."""
        class Spy:
            @property
            def RasterCount(self):
                raise ValueError('not the expected wording')
        monkeypatch.setattr(sa.gdal, 'Open', lambda *a, **k: Spy())
        with pytest.raises(ValueError, match='not the expected wording'):
            _args(input_path=dem, output_path=tmp_path / 'out.tif')

    def test_an_unreadable_input_is_reported_not_swallowed(self, tmp_path, caplog):
        junk = tmp_path / 'junk.tif'
        junk.write_bytes(b'not a raster')
        with caplog.at_level(logging.WARNING):
            _args(input_path=junk, output_path=tmp_path / 'out.tif')
        assert 'band count' in caplog.text

    def test_the_dataset_is_released_on_the_raising_path(self, dem, tmp_path, monkeypatch):
        released = []

        class Spy:
            RasterCount = 3

        spy = Spy()
        weakref.finalize(spy, released.append, True)
        monkeypatch.setattr(sa.gdal, 'Open', lambda *a, **k: spy)
        with pytest.raises(ValueError):
            _args(input_path=dem, output_path=tmp_path / 'out.tif')
        del spy
        gc.collect()
        assert released == [True]
